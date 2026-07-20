from __future__ import annotations

import json
import os
from datetime import datetime, time
from math import isfinite
from typing import Any, Optional
from zoneinfo import ZoneInfo

from scanner.data import prepare_features
from scanner.entry import calculate_trigger_price, validate_direction
from scanner.risk import calculate_trade_levels

IST = ZoneInfo("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(BASE_DIR, "execution_state.json")
MONITOR_START = time(9, 45)
MIN_ROLV = 1.5


def _today_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _now_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


def _to_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _default_state() -> dict:
    return {"date": _today_str(), "version": "V8.0", "stocks": {}}


def load_execution_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return _default_state()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            state = json.load(file)
    except (OSError, json.JSONDecodeError, TypeError):
        return _default_state()
    if not isinstance(state, dict) or state.get("date") != _today_str():
        return _default_state()
    if not isinstance(state.get("stocks"), dict):
        state["stocks"] = {}
    state["version"] = "V8.0"
    return state


def save_execution_state(state: dict) -> bool:
    try:
        temporary_file = f"{STATE_FILE}.tmp"
        with open(temporary_file, "w", encoding="utf-8") as file:
            json.dump(state, file, indent=2, default=str)
        os.replace(temporary_file, STATE_FILE)
        return True
    except OSError as exc:
        print(f"Execution state save error: {exc}")
        return False


def reset_execution_state() -> bool:
    return save_execution_state(_default_state())


def _normalise_watchlist(watchlist: Any) -> list[dict]:
    if watchlist is None:
        return []
    if hasattr(watchlist, "to_dict"):
        try:
            rows = watchlist.to_dict(orient="records")
        except TypeError:
            rows = []
    elif isinstance(watchlist, list):
        rows = watchlist
    else:
        rows = []

    cleaned: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        stock = str(row.get("Stock", "")).strip()
        action = str(row.get("Action", "")).upper().strip()
        if stock and action in {"BUY", "SELL"}:
            cleaned.append({
                "Rank": row.get("Rank"), "Stock": stock, "Action": action,
                "Score": row.get("Score"), "ROLV": row.get("ROLV"), "CMP": row.get("CMP"),
            })
    return cleaned


def _new_stock_state(stock: str, action: str) -> dict:
    return {
        "Stock": stock, "Action": action, "Status": "WAITING",
        "Entry": None, "SL": None, "Target 1": None, "Target 2": None,
        "Risk": None, "Risk %": None, "Live Price": None,
        "Trigger Price": None, "Signal Candle Time": None,
        "Monitoring Started At": f"{_today_str()} 09:45:00",
        "Progress %": None, "Reason": "Waiting for setup confirmation.",
        "Triggered At": None, "Target 1 Hit At": None,
        "Target 2 Hit At": None, "Stop Loss Hit At": None,
        "Last Updated": _now_str(),
    }


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value)
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        return parsed.replace(tzinfo=IST)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text)
            return parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed.astimezone(IST)
        except ValueError:
            return None


def _session_candles(features: dict) -> list[dict]:
    raw = features.get("session_candles", [])
    if not isinstance(raw, list):
        return []
    candles: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        stamp = _parse_time(item.get("time"))
        high, low, close = _to_float(item.get("high")), _to_float(item.get("low")), _to_float(item.get("close"))
        if stamp is None or None in {high, low, close} or stamp.time() < MONITOR_START:
            continue
        candles.append({"time": stamp, "high": high, "low": low, "close": close})
    return sorted(candles, key=lambda candle: candle["time"])


def _progress(action: str, price: Any, entry: Any, target_2: Any) -> Optional[float]:
    price_f, entry_f, target_f = _to_float(price), _to_float(entry), _to_float(target_2)
    if None in {price_f, entry_f, target_f}:
        return None
    total = abs(target_f - entry_f)
    if total <= 0:
        return None
    achieved = price_f - entry_f if action == "BUY" else entry_f - price_f
    return round(max(-100.0, min((achieved / total) * 100, 100.0)), 1)


def _find_trigger(action: str, trigger: float, candles: list[dict]) -> Optional[dict]:
    for candle in candles:
        crossed = candle["high"] >= trigger if action == "BUY" else candle["low"] <= trigger
        if crossed:
            return candle
    return None


def _apply_exit_history(state: dict, candles: list[dict], trigger_time: datetime) -> dict:
    result = state.copy()
    action = str(result.get("Action", "")).upper()
    sl, target_1, target_2 = _to_float(result.get("SL")), _to_float(result.get("Target 1")), _to_float(result.get("Target 2"))
    if None in {sl, target_1, target_2}:
        result.update({"Status": "ERROR", "Reason": "Triggered trade levels are incomplete."})
        return result

    target_1_seen = bool(result.get("Target 1 Hit At"))
    for candle in [c for c in candles if c["time"] > trigger_time]:
        stamp = candle["time"].strftime("%Y-%m-%d %H:%M:%S")
        if action == "BUY":
            stop_hit, t1_hit, t2_hit = candle["low"] <= sl, candle["high"] >= target_1, candle["high"] >= target_2
        else:
            stop_hit, t1_hit, t2_hit = candle["high"] >= sl, candle["low"] <= target_1, candle["low"] <= target_2

        # Conservative OHLC rule: when stop and target occur in one candle,
        # the stop is recorded because intrabar order cannot be verified.
        if stop_hit:
            result.update({"Status": "STOP LOSS HIT", "Stop Loss Hit At": result.get("Stop Loss Hit At") or stamp, "Reason": "Stop-loss reached after entry."})
            return result
        if t2_hit:
            result.update({"Status": "TARGET 2 HIT", "Target 1 Hit At": result.get("Target 1 Hit At") or stamp, "Target 2 Hit At": result.get("Target 2 Hit At") or stamp, "Reason": "Target 2 reached. Trade completed."})
            return result
        if t1_hit and not target_1_seen:
            target_1_seen = True
            result["Target 1 Hit At"] = stamp

    result["Status"] = "TARGET 1 HIT" if target_1_seen else "ACTIVE"
    result["Reason"] = "Target 1 reached; monitoring continues." if target_1_seen else "Trade is active."
    return result


def _initialise_signal(state: dict, action: str, features: dict) -> dict:
    result = state.copy()
    if _to_float(result.get("Trigger Price")) is not None:
        return result
    trigger = calculate_trigger_price(action=action, features=features)
    if trigger is None:
        result.update({"Status": "ERROR", "Reason": "Unable to calculate trigger price."})
        return result
    result["Trigger Price"] = trigger
    result["Signal Candle Time"] = str(features.get("completed_time", ""))
    return result


def evaluate_locked_stock(stock: str, action: str, previous_state: Optional[dict] = None) -> dict:
    """Reconstruct and persist a one-way intraday trade lifecycle."""
    state = (previous_state or _new_stock_state(stock, action)).copy()
    state["Stock"], state["Action"] = stock, action

    features = prepare_features(stock)
    if features is None:
        state.update({"Reason": "Temporary market-data error; prior state preserved.", "Last Updated": _now_str()})
        return state

    live_price = _to_float(features.get("live_price", features.get("cmp")))
    if live_price is None:
        state.update({"Reason": "Live price unavailable; prior state preserved.", "Last Updated": _now_str()})
        return state

    state["Live Price"] = round(live_price, 2)
    state = _initialise_signal(state, action, features)
    trigger = _to_float(state.get("Trigger Price"))
    candles = _session_candles(features)
    if trigger is None:
        state["Last Updated"] = _now_str()
        return state

    trigger_candle = _find_trigger(action, trigger, candles)
    live_crossed = (action == "BUY" and live_price >= trigger) or (action == "SELL" and live_price <= trigger)

    if trigger_candle is None and not live_crossed and not state.get("Triggered At"):
        rolv = _to_float(features.get("rolv"))
        if validate_direction(action=action, features=features) and rolv is not None and rolv >= MIN_ROLV:
            state.update({"Status": "READY", "Reason": "Setup valid; waiting for trigger."})
        else:
            state.update({"Status": "WAITING", "Reason": "Waiting for trend and volume confirmation."})
        state["Progress %"] = None
        state["Last Updated"] = _now_str()
        return state

    trigger_time = _parse_time(state.get("Triggered At"))
    if trigger_time is None and trigger_candle is not None:
        trigger_time = trigger_candle["time"]
        state["Triggered At"] = trigger_time.strftime("%Y-%m-%d %H:%M:%S")
    elif trigger_time is None:
        trigger_time = datetime.now(IST)
        state["Triggered At"] = _now_str()

    if _to_float(state.get("Entry")) is None:
        levels = calculate_trade_levels(action=action, features=features, entry_price=trigger)
        if levels is None:
            state.update({"Status": "ERROR", "Reason": "Trigger found, but risk levels could not be calculated.", "Last Updated": _now_str()})
            return state
        state.update(levels)

    state = _apply_exit_history(state, candles, trigger_time)
    state["Progress %"] = _progress(action, live_price, state.get("Entry"), state.get("Target 2"))
    state["Last Updated"] = _now_str()
    return state


def monitor_watchlist(watchlist: Any) -> list[dict]:
    rows = _normalise_watchlist(watchlist)
    if not rows:
        return []
    state = load_execution_state()
    updated_rows: list[dict] = []
    for row in rows:
        stock, action = row["Stock"], row["Action"]
        previous = state["stocks"].get(stock)
        if previous is None or previous.get("Action") != action:
            previous = _new_stock_state(stock, action)
        result = evaluate_locked_stock(stock, action, previous)
        state["stocks"][stock] = result
        updated_rows.append({
            "Rank": row.get("Rank"), "Stock": stock, "Action": action,
            "Score": row.get("Score"), "ROLV": row.get("ROLV"),
            "CMP": result.get("Live Price", row.get("CMP")), "Status": result.get("Status"),
            "Trigger Price": result.get("Trigger Price"), "Entry": result.get("Entry"), "SL": result.get("SL"),
            "Target 1": result.get("Target 1"), "Target 2": result.get("Target 2"),
            "Progress %": result.get("Progress %"), "Reason": result.get("Reason"),
            "Triggered At": result.get("Triggered At"), "Last Updated": result.get("Last Updated"),
        })
    active = {row["Stock"] for row in rows}
    state["stocks"] = {key: value for key, value in state["stocks"].items() if key in active}
    save_execution_state(state)
    return updated_rows
