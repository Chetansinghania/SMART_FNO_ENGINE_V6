from __future__ import annotations

from math import isfinite
from typing import Any, Optional


ATR_MULTIPLIER = 1.20
MIN_RISK_PCT = 0.0035
DEFAULT_BREAKOUT_BUFFER_PCT = 0.0005
VALID_ACTIONS = {"BUY", "SELL"}


def _to_positive_float(value: Any) -> Optional[float]:
    """Convert a value to a finite positive float."""

    try:
        number = float(value)

    except (TypeError, ValueError):
        return None

    if not isfinite(number) or number <= 0:
        return None

    return number


def _fallback_entry_price(
    action: str,
    features: dict,
    buffer_pct: float,
) -> Optional[float]:
    """
    Create a temporary breakout entry for V6 compatibility.

    In V7, the actual triggered entry price will normally be passed
    directly from entry.py.
    """

    live_price = _to_positive_float(
        features.get(
            "live_price",
            features.get("cmp"),
        )
    )

    completed_high = _to_positive_float(
        features.get(
            "completed_high",
            features.get("latest_high"),
        )
    )

    completed_low = _to_positive_float(
        features.get(
            "completed_low",
            features.get("latest_low"),
        )
    )

    if (
        live_price is None
        or completed_high is None
        or completed_low is None
        or buffer_pct < 0
    ):
        return None

    buffer_value = live_price * buffer_pct

    if action == "BUY":
        return round(
            completed_high + buffer_value,
            2,
        )

    if action == "SELL":
        return round(
            completed_low - buffer_value,
            2,
        )

    return None


def calculate_trade_levels(
    action: str,
    features: dict,
    entry_price: Optional[float] = None,
    atr_multiplier: float = ATR_MULTIPLIER,
    min_risk_pct: float = MIN_RISK_PCT,
    breakout_buffer_pct: float = DEFAULT_BREAKOUT_BUFFER_PCT,
) -> Optional[dict]:
    """
    Calculate stop-loss and targets after an entry is available.

    Preferred V7 usage:

        calculate_trade_levels(
            action="BUY",
            features=features,
            entry_price=entry_result["Entry"],
        )

    Temporary V6 compatibility:

        If entry_price is not supplied, the function derives an entry
        from the completed candle high or low.

    Risk model:

        Risk distance = maximum of:
        - 1.20 × ATR
        - 0.35% of entry price

        Target 1 = 1R
        Target 2 = 2R
    """

    if not isinstance(features, dict):
        return None

    action = str(action).upper().strip()

    if action not in VALID_ACTIONS:
        return None

    atr = _to_positive_float(
        features.get("atr")
    )

    if atr is None:
        return None

    if atr_multiplier <= 0 or min_risk_pct <= 0:
        return None

    entry = _to_positive_float(entry_price)

    # Temporary compatibility with the current engine.py.
    if entry is None:
        entry = _fallback_entry_price(
            action=action,
            features=features,
            buffer_pct=breakout_buffer_pct,
        )

    if entry is None:
        return None

    atr_risk = atr * atr_multiplier
    percentage_risk = entry * min_risk_pct

    risk_distance = max(
        atr_risk,
        percentage_risk,
    )

    if (
        not isfinite(risk_distance)
        or risk_distance <= 0
    ):
        return None

    if action == "BUY":

        stop_loss = entry - risk_distance
        target_1 = entry + risk_distance
        target_2 = entry + (2 * risk_distance)

    else:

        stop_loss = entry + risk_distance
        target_1 = entry - risk_distance
        target_2 = entry - (2 * risk_distance)

    if min(
        stop_loss,
        target_1,
        target_2,
    ) <= 0:
        return None

    return {
        "Entry": round(entry, 2),
        "SL": round(stop_loss, 2),
        "Target 1": round(target_1, 2),
        "Target 2": round(target_2, 2),
        "Risk": round(risk_distance, 2),
        "Risk %": round(
            (risk_distance / entry) * 100,
            2,
        ),
    }