from __future__ import annotations

import json
import os
from datetime import datetime
from math import isfinite
from typing import Any, Optional
from zoneinfo import ZoneInfo

from scanner.data import prepare_features
from scanner.entry import evaluate_entry
from scanner.risk import calculate_trade_levels


IST = ZoneInfo("Asia/Kolkata")

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

STATE_FILE = os.path.join(
    BASE_DIR,
    "execution_state.json",
)

ENTRY_STATES = {
    "WAITING",
    "READY",
    "TRIGGERED",
    "EXPIRED",
    "ERROR",
}

ACTIVE_STATES = {
    "TRIGGERED",
    "ACTIVE",
    "TARGET 1 HIT",
}

FINAL_STATES = {
    "TARGET 2 HIT",
    "STOP LOSS HIT",
    "EXPIRED",
}


def _today_str() -> str:
    """Return the current Indian date in ISO format."""

    return datetime.now(IST).strftime("%Y-%m-%d")


def _now_str() -> str:
    """Return the current Indian date and time."""

    return datetime.now(IST).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _to_float(value: Any) -> Optional[float]:
    """Convert a value to a finite float."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not isfinite(number):
        return None

    return number


def _default_state() -> dict:
    """Create an empty daily execution state."""

    return {
        "date": _today_str(),
        "stocks": {},
    }


def load_execution_state() -> dict:
    """
    Load today's execution state.

    State from an earlier day is discarded automatically.
    """

    if not os.path.exists(STATE_FILE):
        return _default_state()

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            state = json.load(file)

    except (
        OSError,
        json.JSONDecodeError,
        TypeError,
    ):
        return _default_state()

    if not isinstance(state, dict):
        return _default_state()

    if state.get("date") != _today_str():
        return _default_state()

    if not isinstance(state.get("stocks"), dict):
        state["stocks"] = {}

    return state


def save_execution_state(state: dict) -> bool:
    """Save execution state atomically."""

    try:
        temporary_file = f"{STATE_FILE}.tmp"

        with open(
            temporary_file,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                state,
                file,
                indent=2,
                default=str,
            )

        os.replace(
            temporary_file,
            STATE_FILE,
        )

        return True

    except OSError as exc:
        print(f"Execution state save error: {exc}")
        return False


def reset_execution_state() -> bool:
    """Reset today's execution state."""

    return save_execution_state(
        _default_state()
    )


def _normalise_watchlist(
    watchlist: Any,
) -> list[dict]:
    """Convert a dataframe or list into clean watchlist rows."""

    if watchlist is None:
        return []

    if hasattr(watchlist, "to_dict"):
        try:
            rows = watchlist.to_dict(
                orient="records"
            )
        except TypeError:
            rows = []
    elif isinstance(watchlist, list):
        rows = watchlist
    else:
        rows = []

    cleaned_rows: list[dict] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        stock = str(
            row.get("Stock", "")
        ).strip()

        action = str(
            row.get("Action", "")
        ).upper().strip()

        if not stock or action not in {"BUY", "SELL"}:
            continue

        cleaned_rows.append(
            {
                "Rank": row.get("Rank"),
                "Stock": stock,
                "Action": action,
                "Score": row.get("Score"),
                "ROLV": row.get("ROLV"),
                "CMP": row.get("CMP"),
            }
        )

    return cleaned_rows


def _new_stock_state(
    stock: str,
    action: str,
) -> dict:
    """Create initial execution state for one stock."""

    return {
        "Stock": stock,
        "Action": action,
        "Status": "WAITING",
        "Entry": None,
        "SL": None,
        "Target 1": None,
        "Target 2": None,
        "Risk": None,
        "Risk %": None,
        "Live Price": None,
        "Trigger Price": None,
        "Points to Trigger": None,
        "Trigger Distance %": None,
        "Progress %": None,
        "Reason": "Waiting for market evaluation.",
        "Triggered At": None,
        "Target 1 Hit At": None,
        "Target 2 Hit At": None,
        "Stop Loss Hit At": None,
        "Last Updated": _now_str(),
    }


def _calculate_trigger_distance(
    action: str,
    live_price: Any,
    trigger_price: Any,
) -> tuple[Optional[float], Optional[float]]:
    """
    Return remaining points and percentage to trigger.

    Positive values mean the trigger has not been reached.
    Zero means the price has reached or crossed the trigger.
    """

    live = _to_float(live_price)
    trigger = _to_float(trigger_price)

    if live is None or trigger is None or trigger <= 0:
        return None, None

    if action == "BUY":
        points = max(trigger - live, 0.0)
    else:
        points = max(live - trigger, 0.0)

    percentage = (points / trigger) * 100

    return round(points, 2), round(percentage, 3)


def _trade_progress(
    action: str,
    live_price: Any,
    entry: Any,
    target_2: Any,
) -> Optional[float]:
    """Return progress from entry to Target 2 as a percentage."""

    live = _to_float(live_price)
    entry_price = _to_float(entry)
    final_target = _to_float(target_2)

    if (
        live is None
        or entry_price is None
        or final_target is None
    ):
        return None

    total_move = abs(final_target - entry_price)

    if total_move <= 0:
        return None

    if action == "BUY":
        achieved_move = live - entry_price
    else:
        achieved_move = entry_price - live

    progress = (achieved_move / total_move) * 100

    return round(
        max(-100.0, min(progress, 100.0)),
        1,
    )


def _manage_active_trade(
    state: dict,
    live_price: float,
) -> dict:
    """Update an already-triggered trade through its lifecycle."""

    result = state.copy()
    action = str(result.get("Action", "")).upper()

    entry = _to_float(result.get("Entry"))
    stop_loss = _to_float(result.get("SL"))
    target_1 = _to_float(result.get("Target 1"))
    target_2 = _to_float(result.get("Target 2"))

    if None in {
        entry,
        stop_loss,
        target_1,
        target_2,
    }:
        result.update(
            {
                "Status": "ERROR",
                "Reason": "Active trade levels are incomplete.",
                "Last Updated": _now_str(),
            }
        )
        return result

    previous_status = result.get("Status")

    if action == "BUY":
        stop_hit = live_price <= stop_loss
        target_1_hit = live_price >= target_1
        target_2_hit = live_price >= target_2
    else:
        stop_hit = live_price >= stop_loss
        target_1_hit = live_price <= target_1
        target_2_hit = live_price <= target_2

    # With only the latest price available, the first visible terminal
    # condition is recorded. Target 2 receives priority over Target 1.
    if target_2_hit:
        result.update(
            {
                "Status": "TARGET 2 HIT",
                "Target 1 Hit At": (
                    result.get("Target 1 Hit At")
                    or _now_str()
                ),
                "Target 2 Hit At": (
                    result.get("Target 2 Hit At")
                    or _now_str()
                ),
                "Reason": "Target 2 reached. Trade completed.",
            }
        )

    elif stop_hit:
        result.update(
            {
                "Status": "STOP LOSS HIT",
                "Stop Loss Hit At": (
                    result.get("Stop Loss Hit At")
                    or _now_str()
                ),
                "Reason": "Stop-loss level reached. Trade closed.",
            }
        )

    elif target_1_hit or previous_status == "TARGET 1 HIT":
        result.update(
            {
                "Status": "TARGET 1 HIT",
                "Target 1 Hit At": (
                    result.get("Target 1 Hit At")
                    or _now_str()
                ),
                "Reason": (
                    "Target 1 reached; monitoring continues "
                    "for Target 2 or stop-loss."
                ),
            }
        )

    else:
        result.update(
            {
                "Status": "ACTIVE",
                "Reason": "Trade is active between entry and exit levels.",
            }
        )

    result["Live Price"] = round(live_price, 2)
    result["Progress %"] = _trade_progress(
        action=action,
        live_price=live_price,
        entry=entry,
        target_2=target_2,
    )
    result["Points to Trigger"] = 0.0
    result["Trigger Distance %"] = 0.0
    result["Last Updated"] = _now_str()

    return result


def evaluate_locked_stock(
    stock: str,
    action: str,
    previous_state: Optional[dict] = None,
) -> dict:
    """
    Evaluate one locked stock and manage its complete trade lifecycle.

    Final states remain frozen for the rest of the trading day.
    """

    if previous_state is None:
        previous_state = _new_stock_state(
            stock,
            action,
        )

    previous_status = str(
        previous_state.get("Status", "WAITING")
    ).upper()

    if previous_status in FINAL_STATES:
        previous_state["Last Updated"] = _now_str()
        return previous_state

    features = prepare_features(stock)

    if features is None:
        result = previous_state.copy()

        # Do not destroy a valid active trade because of a temporary
        # data-download failure.
        if previous_status in ACTIVE_STATES:
            result.update(
                {
                    "Reason": (
                        "Temporary data error; previous trade "
                        "state has been preserved."
                    ),
                    "Last Updated": _now_str(),
                }
            )
            return result

        result.update(
            {
                "Status": "ERROR",
                "Reason": "Unable to prepare current market features.",
                "Last Updated": _now_str(),
            }
        )
        return result

    live_price = _to_float(
        features.get(
            "live_price",
            features.get("cmp"),
        )
    )

    if live_price is None:
        result = previous_state.copy()
        result.update(
            {
                "Status": "ERROR",
                "Reason": "Live price is unavailable.",
                "Last Updated": _now_str(),
            }
        )
        return result

    if previous_status in ACTIVE_STATES:
        return _manage_active_trade(
            state=previous_state,
            live_price=live_price,
        )

    entry_result = evaluate_entry(
        action=action,
        features=features,
    )

    status = str(
        entry_result.get("Status", "ERROR")
    ).upper()

    if status not in ENTRY_STATES:
        status = "ERROR"

    trigger_price = entry_result.get(
        "Trigger Price"
    )

    points_to_trigger, distance_pct = (
        _calculate_trigger_distance(
            action=action,
            live_price=live_price,
            trigger_price=trigger_price,
        )
    )

    result = previous_state.copy()

    result.update(
        {
            "Stock": stock,
            "Action": action,
            "Status": status,
            "Live Price": round(live_price, 2),
            "Trigger Price": trigger_price,
            "Points to Trigger": points_to_trigger,
            "Trigger Distance %": distance_pct,
            "Reason": entry_result.get(
                "Reason",
                "",
            ),
            "Last Updated": _now_str(),
        }
    )

    if status != "TRIGGERED":
        return result

    entry_price = entry_result.get("Entry")

    levels = calculate_trade_levels(
        action=action,
        features=features,
        entry_price=entry_price,
    )

    if levels is None:
        result.update(
            {
                "Status": "ERROR",
                "Reason": (
                    "Entry triggered, but risk levels "
                    "could not be calculated."
                ),
            }
        )
        return result

    result.update(
        {
            "Entry": levels["Entry"],
            "SL": levels["SL"],
            "Target 1": levels["Target 1"],
            "Target 2": levels["Target 2"],
            "Risk": levels.get("Risk"),
            "Risk %": levels.get("Risk %"),
            "Points to Trigger": 0.0,
            "Trigger Distance %": 0.0,
            "Progress %": 0.0,
            "Triggered At": (
                previous_state.get("Triggered At")
                or _now_str()
            ),
            "Reason": entry_result.get(
                "Reason",
                "Breakout trigger crossed.",
            ),
        }
    )

    return result


def monitor_watchlist(
    watchlist: Any,
) -> list[dict]:
    """
    Monitor the locked watchlist and return dashboard-ready rows.
    """

    rows = _normalise_watchlist(
        watchlist
    )

    if not rows:
        return []

    state = load_execution_state()
    updated_rows: list[dict] = []

    for row in rows:
        stock = row["Stock"]
        action = row["Action"]

        previous_state = state["stocks"].get(
            stock
        )

        if (
            previous_state is None
            or previous_state.get("Action") != action
        ):
            previous_state = _new_stock_state(
                stock,
                action,
            )

        execution_result = evaluate_locked_stock(
            stock=stock,
            action=action,
            previous_state=previous_state,
        )

        state["stocks"][stock] = execution_result

        updated_rows.append(
            {
                "Rank": row.get("Rank"),
                "Stock": stock,
                "Action": action,
                "Score": row.get("Score"),
                "ROLV": row.get("ROLV"),
                "CMP": execution_result.get(
                    "Live Price",
                    row.get("CMP"),
                ),
                "Status": execution_result.get("Status"),
                "Trigger Price": execution_result.get(
                    "Trigger Price"
                ),
                "Points to Trigger": execution_result.get(
                    "Points to Trigger"
                ),
                "Trigger Distance %": execution_result.get(
                    "Trigger Distance %"
                ),
                "Entry": execution_result.get("Entry"),
                "SL": execution_result.get("SL"),
                "Target 1": execution_result.get("Target 1"),
                "Target 2": execution_result.get("Target 2"),
                "Progress %": execution_result.get(
                    "Progress %"
                ),
                "Reason": execution_result.get("Reason"),
                "Triggered At": execution_result.get(
                    "Triggered At"
                ),
                "Last Updated": execution_result.get(
                    "Last Updated"
                ),
            }
        )

    active_symbols = {
        row["Stock"]
        for row in rows
    }

    state["stocks"] = {
        stock: stock_state
        for stock, stock_state in state["stocks"].items()
        if stock in active_symbols
    }

    save_execution_state(state)

    return updated_rows
