from __future__ import annotations

from math import isfinite
from typing import Any, Optional

ATR_MULTIPLIER = 1.20
MIN_RISK_PCT = 0.0035
MAX_RISK_PCT = 0.0100
STRUCTURE_BUFFER_PCT = 0.0005
VALID_ACTIONS = {"BUY", "SELL"}


def _positive(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and number > 0 else None


def calculate_trade_levels(action: str, features: dict, entry_price: Optional[float] = None,
                           atr_multiplier: float = ATR_MULTIPLIER,
                           min_risk_pct: float = MIN_RISK_PCT,
                           max_risk_pct: float = MAX_RISK_PCT,
                           **_: Any) -> Optional[dict]:
    """Create structure-aware 1R/2R trade levels and reject excessive risk."""
    if not isinstance(features, dict):
        return None
    action = str(action).upper().strip()
    if action not in VALID_ACTIONS:
        return None

    entry = _positive(entry_price)
    atr = _positive(features.get("atr"))
    high = _positive(features.get("completed_high", features.get("latest_high")))
    low = _positive(features.get("completed_low", features.get("latest_low")))
    if None in {entry, atr, high, low} or atr_multiplier <= 0:
        return None

    buffer_value = entry * STRUCTURE_BUFFER_PCT
    minimum_distance = max(atr * atr_multiplier, entry * min_risk_pct)
    if action == "BUY":
        structure_sl = low - buffer_value
        risk_distance = max(minimum_distance, entry - structure_sl)
        sl = entry - risk_distance
        t1, t2 = entry + risk_distance, entry + 2 * risk_distance
    else:
        structure_sl = high + buffer_value
        risk_distance = max(minimum_distance, structure_sl - entry)
        sl = entry + risk_distance
        t1, t2 = entry - risk_distance, entry - 2 * risk_distance

    risk_pct = risk_distance / entry
    if not isfinite(risk_distance) or risk_distance <= 0 or risk_pct > max_risk_pct:
        return None
    if min(sl, t1, t2) <= 0:
        return None

    return {
        "Entry": round(entry, 2), "SL": round(sl, 2),
        "Target 1": round(t1, 2), "Target 2": round(t2, 2),
        "Risk": round(risk_distance, 2), "Risk %": round(risk_pct * 100, 2),
    }
