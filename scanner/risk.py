def calculate_trade_levels(action, features):
    cmp_price = features["cmp"]
    atr = features["atr"]

    if atr is None or atr <= 0:
        return None

    buffer = cmp_price * 0.0005

    if action == "BUY":
        entry = round(features["latest_high"] + buffer, 2)
        sl = round(entry - atr, 2)
        risk = entry - sl
        target1 = round(entry + risk, 2)
        target2 = round(entry + (risk * 2), 2)

    elif action == "SELL":
        entry = round(features["latest_low"] - buffer, 2)
        sl = round(entry + atr, 2)
        risk = sl - entry
        target1 = round(entry - risk, 2)
        target2 = round(entry - (risk * 2), 2)

    else:
        return None

    if risk <= 0:
        return None

    return {
        "Entry": entry,
        "SL": sl,
        "Target 1": target1,
        "Target 2": target2
    }