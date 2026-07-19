from __future__ import annotations

from typing import Any, Optional

from scanner.data import prepare_features


MIN_STOCK_PRICE = 2500.0
MIN_SCORE = 70
MAX_SELECTIONS = 2
MIN_ROLV = 1.5


def _to_float(value: Any) -> Optional[float]:
    """Safely convert a value to float."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number != number:
        return None

    return number


def _extract_scoring_values(
    features: dict,
) -> Optional[dict[str, float]]:
    """Validate and extract the values required for stock scoring."""

    if not isinstance(features, dict):
        return None

    raw_values = {
        "cmp": features.get(
            "live_price",
            features.get("cmp"),
        ),
        "ema20": features.get("ema20"),
        "ema50": features.get("ema50"),
        "vwap": features.get("vwap"),
        "rolv": features.get("rolv"),
        "today_high": features.get("today_high"),
        "today_low": features.get("today_low"),
        "latest_close": features.get(
            "completed_close",
            features.get("latest_close"),
        ),
        "prev_close": features.get(
            "previous_close",
            features.get("prev_close"),
        ),
    }

    values: dict[str, float] = {}

    for key, raw_value in raw_values.items():
        value = _to_float(raw_value)

        if value is None:
            return None

        values[key] = value

    if values["today_high"] <= values["today_low"]:
        return None

    return values


def score_stock(features: dict) -> Optional[dict]:
    """
    Score one stock for BUY and SELL strength.

    This function performs selection scoring only.
    It does not calculate Entry, SL, or Targets.
    """

    values = _extract_scoring_values(features)

    if values is None:
        return None

    cmp_price = values["cmp"]
    ema20 = values["ema20"]
    ema50 = values["ema50"]
    vwap = values["vwap"]
    rolv = values["rolv"]
    today_high = values["today_high"]
    today_low = values["today_low"]
    latest_close = values["latest_close"]
    prev_close = values["prev_close"]

    buy_score = 0
    sell_score = 0

    # BUY strength
    if cmp_price > ema20:
        buy_score += 20

    if cmp_price > ema50:
        buy_score += 15

    if cmp_price > vwap:
        buy_score += 20

    if latest_close > prev_close:
        buy_score += 10

    if rolv >= MIN_ROLV:
        buy_score += 20

    session_range = today_high - today_low
    position = (cmp_price - today_low) / session_range

    if position > 0.55:
        buy_score += 15

    # SELL strength
    if cmp_price < ema20:
        sell_score += 20

    if cmp_price < ema50:
        sell_score += 15

    if cmp_price < vwap:
        sell_score += 20

    if latest_close < prev_close:
        sell_score += 10

    if rolv >= MIN_ROLV:
        sell_score += 20

    if position < 0.45:
        sell_score += 15

    if buy_score >= sell_score:
        action = "BUY"
        final_score = buy_score
        opposite_score = sell_score
    else:
        action = "SELL"
        final_score = sell_score
        opposite_score = buy_score

    return {
        "Action": action,
        "Score": final_score,
        "Opposite Score": opposite_score,
        "ROLV": round(rolv, 2),
        "CMP": round(cmp_price, 2),
    }


def scan_market(stocks) -> list[dict]:
    """
    Scan the universe and return only the Top 2 watchlist candidates.

    The returned rows intentionally do not contain Entry, SL, or Targets.
    Trade levels will be created later by entry.py and risk.py after a
    valid breakout trigger.
    """

    results: list[dict] = []

    for symbol in stocks:
        try:
            features = prepare_features(symbol)

            if features is None:
                continue

            cmp_price = _to_float(
                features.get(
                    "live_price",
                    features.get("cmp"),
                )
            )

            if cmp_price is None:
                continue

            if cmp_price < MIN_STOCK_PRICE:
                continue

            score_result = score_stock(features)

            if score_result is None:
                continue

            score = int(score_result["Score"])

            if score < MIN_SCORE:
                continue

            results.append(
                {
                    "Stock": symbol,
                    "Action": score_result["Action"],
                    "Score": score,
                    "ROLV": score_result["ROLV"],
                    "CMP": score_result["CMP"],
                    "Status": "WAITING",
                    "_score": score,
                    "_opposite_score": int(
                        score_result["Opposite Score"]
                    ),
                }
            )

        except (KeyError, TypeError, ValueError):
            continue

        except Exception as exc:
            print(f"Scanner error for {symbol}: {exc}")
            continue

    results.sort(
        key=lambda row: (
            row["_score"],
            row["ROLV"],
        ),
        reverse=True,
    )

    top_results = results[:MAX_SELECTIONS]

    final_results: list[dict] = []

    for rank, row in enumerate(top_results, start=1):
        final_results.append(
            {
                "Rank": rank,
                "Stock": row["Stock"],
                "Action": row["Action"],
                "Score": row["Score"],
                "ROLV": row["ROLV"],
                "CMP": row["CMP"],
                "Status": row["Status"],
            }
        )

    return final_results
