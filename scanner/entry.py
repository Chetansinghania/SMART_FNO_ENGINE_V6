from __future__ import annotations

from typing import Any, Optional


DEFAULT_BREAKOUT_BUFFER_PCT = 0.0005
DEFAULT_MIN_ROLV = 1.5
VALID_ACTIONS = {"BUY", "SELL"}


def _to_float(value: Any) -> Optional[float]:
    """Safely convert a value to float."""

    try:
        number = float(value)

    except (TypeError, ValueError):
        return None

    if number != number:
        return None

    return number


def _required_values(
    features: dict,
) -> Optional[dict[str, float]]:
    """Validate the values required by the entry engine."""

    if not isinstance(features, dict):
        return None

    raw_values = {
        "live_price": features.get(
            "live_price",
            features.get("cmp"),
        ),
        "completed_high": features.get(
            "completed_high",
            features.get("latest_high"),
        ),
        "completed_low": features.get(
            "completed_low",
            features.get("latest_low"),
        ),
        "completed_close": features.get(
            "completed_close",
            features.get("latest_close"),
        ),
        "previous_close": features.get(
            "previous_close",
            features.get("prev_close"),
        ),
        "ema20": features.get("ema20"),
        "ema50": features.get("ema50"),
        "vwap": features.get("vwap"),
        "rolv": features.get("rolv"),
    }

    values: dict[str, float] = {}

    for key, raw_value in raw_values.items():

        value = _to_float(raw_value)

        if value is None:
            return None

        values[key] = value

    if values["completed_high"] <= values["completed_low"]:
        return None

    return values


def validate_direction(
    action: str,
    features: dict,
) -> bool:
    """
    Confirm whether the completed candle supports the selected direction.
    """

    action = str(action).upper().strip()

    values = _required_values(features)

    if action not in VALID_ACTIONS:
        return False

    if values is None:
        return False

    close = values["completed_close"]
    ema20 = values["ema20"]
    ema50 = values["ema50"]
    vwap = values["vwap"]

    if action == "BUY":

        return (
            close > ema20
            and ema20 > ema50
            and close > vwap
        )

    return (
        close < ema20
        and ema20 < ema50
        and close < vwap
    )


def calculate_trigger_price(
    action: str,
    features: dict,
    buffer_pct: float = DEFAULT_BREAKOUT_BUFFER_PCT,
) -> Optional[float]:
    """
    Calculate the breakout price from the latest completed candle.
    """

    action = str(action).upper().strip()

    values = _required_values(features)

    if action not in VALID_ACTIONS:
        return None

    if values is None:
        return None

    if buffer_pct < 0:
        return None

    reference_price = values["completed_close"]

    buffer_value = reference_price * buffer_pct

    if action == "BUY":

        trigger_price = (
            values["completed_high"]
            + buffer_value
        )

    else:

        trigger_price = (
            values["completed_low"]
            - buffer_value
        )

    return round(trigger_price, 2)


def evaluate_entry(
    action: str,
    features: dict,
    buffer_pct: float = DEFAULT_BREAKOUT_BUFFER_PCT,
    min_rolv: float = DEFAULT_MIN_ROLV,
) -> dict:
    """
    Evaluate one locked stock and return its entry status.

    Status:

    WAITING
        The completed candle does not confirm the setup yet.

    READY
        The setup is valid, but price has not crossed the trigger.

    TRIGGERED
        The breakout trigger has been crossed.

    EXPIRED
        Price invalidated the setup before triggering.

    ERROR
        Required market data is missing or invalid.
    """

    action = str(action).upper().strip()

    symbol = str(
        features.get("symbol", "")
    ).strip()

    values = _required_values(features)

    result = {
        "Symbol": symbol,
        "Action": action,
        "Status": "ERROR",
        "Entry": None,
        "Live Price": None,
        "Trigger Price": None,
        "Reason": "Invalid or incomplete market data.",
    }

    if action not in VALID_ACTIONS:

        result["Reason"] = (
            "Action must be BUY or SELL."
        )

        return result

    if values is None:
        return result

    live_price = values["live_price"]
    rolv = values["rolv"]

    trigger_price = calculate_trigger_price(
        action=action,
        features=features,
        buffer_pct=buffer_pct,
    )

    result["Live Price"] = round(
        live_price,
        2,
    )

    result["Trigger Price"] = trigger_price

    if trigger_price is None:

        result["Reason"] = (
            "Unable to calculate breakout trigger."
        )

        return result

    # Expire a BUY setup when price breaks below
    # the completed signal candle low before triggering.
    if (
        action == "BUY"
        and live_price <= values["completed_low"]
    ):

        result["Status"] = "EXPIRED"

        result["Reason"] = (
            "Price broke below the signal candle low."
        )

        return result

    # Expire a SELL setup when price breaks above
    # the completed signal candle high before triggering.
    if (
        action == "SELL"
        and live_price >= values["completed_high"]
    ):

        result["Status"] = "EXPIRED"

        result["Reason"] = (
            "Price broke above the signal candle high."
        )

        return result

    if not validate_direction(
        action=action,
        features=features,
    ):

        result["Status"] = "WAITING"

        result["Reason"] = (
            "Waiting for EMA20, EMA50 and VWAP "
            "confirmation on a completed 15-minute candle."
        )

        return result

    if rolv < min_rolv:

        result["Status"] = "WAITING"

        result["Reason"] = (
            f"Waiting for ROLV to reach {min_rolv:.2f}. "
            f"Current ROLV is {rolv:.2f}."
        )

        return result

    if (
        action == "BUY"
        and live_price >= trigger_price
    ):

        result["Status"] = "TRIGGERED"
        result["Entry"] = trigger_price

        result["Reason"] = (
            "BUY breakout trigger crossed."
        )

        return result

    if (
        action == "SELL"
        and live_price <= trigger_price
    ):

        result["Status"] = "TRIGGERED"
        result["Entry"] = trigger_price

        result["Reason"] = (
            "SELL breakdown trigger crossed."
        )

        return result

    result["Status"] = "READY"

    result["Reason"] = (
        "Setup confirmed; waiting for breakout trigger."
    )

    return result