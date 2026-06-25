import yfinance as yf
import pandas as pd


def get_intraday_data(symbol, period="5d", interval="15m"):
    try:
        data = yf.download(
            symbol,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True
        )

        if data is None or data.empty:
            return None

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        return data.dropna()

    except Exception as e:
        print("Data error:", symbol, e)
        return None


def get_last_price(symbol):
    data = get_intraday_data(symbol, period="1d", interval="5m")

    if data is None or data.empty:
        return None

    return round(float(data["Close"].iloc[-1]), 2)


def calculate_vwap(data):
    typical_price = (data["High"] + data["Low"] + data["Close"]) / 3
    date_group = data.index.date

    return (
        (typical_price * data["Volume"]).groupby(date_group).cumsum()
        / data["Volume"].groupby(date_group).cumsum()
    )


def calculate_atr(data, period=14):
    prev_close = data["Close"].shift(1)

    tr = pd.concat([
        data["High"] - data["Low"],
        (data["High"] - prev_close).abs(),
        (data["Low"] - prev_close).abs()
    ], axis=1).max(axis=1)

    return tr.rolling(period).mean()


def prepare_features(symbol):
    data = get_intraday_data(symbol)

    if data is None or len(data) < 50:
        return None

    data["EMA20"] = data["Close"].ewm(span=20).mean()
    data["EMA50"] = data["Close"].ewm(span=50).mean()
    data["VWAP"] = calculate_vwap(data)
    data["ATR"] = calculate_atr(data)
    data["AVG_VOLUME"] = data["Volume"].rolling(20).mean()
    data["ROLV"] = data["Volume"] / data["AVG_VOLUME"]

    data = data.dropna()

    if data.empty:
        return None

    today = pd.Timestamp.now(tz="Asia/Kolkata").date()
    today_data = data[data.index.date == today]

    if today_data.empty:
        return None

    latest = data.iloc[-1]

    return {
        "symbol": symbol,
        "data": data,
        "today_data": today_data,
        "cmp": round(float(latest["Close"]), 2),
        "ema20": float(latest["EMA20"]),
        "ema50": float(latest["EMA50"]),
        "vwap": float(latest["VWAP"]),
        "atr": float(latest["ATR"]),
        "rolv": float(latest["ROLV"]),
        "today_high": float(today_data["High"].max()),
        "today_low": float(today_data["Low"].min()),
        "latest_high": float(latest["High"]),
        "latest_low": float(latest["Low"]),
        "latest_close": float(latest["Close"]),
        "prev_close": float(data["Close"].iloc[-2]),
    }