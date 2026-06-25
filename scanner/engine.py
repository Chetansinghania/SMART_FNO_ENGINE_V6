from scanner.data import prepare_features
from scanner.risk import calculate_trade_levels


def score_stock(features):
    cmp_price = features["cmp"]
    ema20 = features["ema20"]
    ema50 = features["ema50"]
    vwap = features["vwap"]
    rolv = features["rolv"]
    today_high = features["today_high"]
    today_low = features["today_low"]
    latest_close = features["latest_close"]
    prev_close = features["prev_close"]

    buy_score = 0
    sell_score = 0

    if cmp_price > ema20:
        buy_score += 20
    if cmp_price > ema50:
        buy_score += 15
    if cmp_price > vwap:
        buy_score += 20
    if latest_close > prev_close:
        buy_score += 10
    if rolv >= 1.5:
        buy_score += 20
    if today_high > today_low:
        position = (cmp_price - today_low) / (today_high - today_low)
        if position > 0.55:
            buy_score += 15

    if cmp_price < ema20:
        sell_score += 20
    if cmp_price < ema50:
        sell_score += 15
    if cmp_price < vwap:
        sell_score += 20
    if latest_close < prev_close:
        sell_score += 10
    if rolv >= 1.5:
        sell_score += 20
    if today_high > today_low:
        position = (cmp_price - today_low) / (today_high - today_low)
        if position < 0.45:
            sell_score += 15

    if buy_score >= sell_score:
        return "BUY", buy_score
    else:
        return "SELL", sell_score


def scan_market(stocks):
    results = []

    for symbol in stocks:
        features = prepare_features(symbol)

        if features is None:
            continue

        if features["cmp"] < 2500:
            continue

        action, score = score_stock(features)

        if score < 70:
            continue

        levels = calculate_trade_levels(action, features)

        if levels is None:
            continue

        results.append({
            "Stock": symbol,
            "Action": action,
            "Entry": levels["Entry"],
            "SL": levels["SL"],
            "Target 1": levels["Target 1"],
            "Target 2": levels["Target 2"],
            "_score": score
        })

    results = sorted(results, key=lambda x: x["_score"], reverse=True)

    for row in results:
        row.pop("_score", None)

    return results[:3]