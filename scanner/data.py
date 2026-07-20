from __future__ import annotations

from datetime import timedelta
from typing import Optional

import pandas as pd
import yfinance as yf


IST = "Asia/Kolkata"
DEFAULT_INTERVAL_MINUTES = 15


def get_intraday_data(
    symbol: str,
    period: str = "5d",
    interval: str = "15m",
) -> Optional[pd.DataFrame]:
    """Download and clean intraday OHLCV data for one stock."""

    try:
        data = yf.download(
            tickers=symbol,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
            threads=False,
        )

        if data is None or data.empty:
            return None

        # Handle MultiIndex columns returned by yfinance.
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        required_columns = {
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        }

        if not required_columns.issubset(data.columns):
            return None

        data = data[
            ["Open", "High", "Low", "Close", "Volume"]
        ].copy()

        data = data.dropna(
            subset=["Open", "High", "Low", "Close", "Volume"]
        )

        data = data[
            ~data.index.duplicated(keep="last")
        ].sort_index()

        if data.empty:
            return None

        return data

    except Exception as exc:
        print(f"Data download error for {symbol}: {exc}")
        return None


def _index_in_ist(data: pd.DataFrame) -> pd.DatetimeIndex:
    """Convert dataframe timestamps to Indian Standard Time."""

    index = pd.DatetimeIndex(data.index)

    if index.tz is None:
        return index.tz_localize(IST)

    return index.tz_convert(IST)


def get_last_price(symbol: str) -> Optional[float]:
    """Return the latest available approximate market price."""

    data = get_intraday_data(
        symbol=symbol,
        period="5d",
        interval="5m",
    )

    if data is None or data.empty:
        return None

    try:
        return round(float(data["Close"].iloc[-1]), 2)

    except (ValueError, TypeError, IndexError):
        return None


def calculate_vwap(data: pd.DataFrame) -> pd.Series:
    """Calculate VWAP separately for every trading session."""

    typical_price = (
        data["High"]
        + data["Low"]
        + data["Close"]
    ) / 3

    session_dates = pd.Series(
        _index_in_ist(data).date,
        index=data.index,
    )

    traded_value = typical_price * data["Volume"]

    cumulative_value = traded_value.groupby(
        session_dates
    ).cumsum()

    cumulative_volume = data["Volume"].groupby(
        session_dates
    ).cumsum()

    cumulative_volume = cumulative_volume.replace(
        0,
        float("nan"),
    )

    return cumulative_value / cumulative_volume


def calculate_atr(
    data: pd.DataFrame,
    period: int = 14,
) -> pd.Series:
    """Calculate Average True Range."""

    previous_close = data["Close"].shift(1)

    high_low = data["High"] - data["Low"]

    high_previous_close = (
        data["High"] - previous_close
    ).abs()

    low_previous_close = (
        data["Low"] - previous_close
    ).abs()

    true_range = pd.concat(
        [
            high_low,
            high_previous_close,
            low_previous_close,
        ],
        axis=1,
    ).max(axis=1)

    return true_range.rolling(
        window=period,
        min_periods=period,
    ).mean()


def _completed_candles(
    data: pd.DataFrame,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
) -> pd.DataFrame:
    """
    Return only completed candles.

    Yahoo Finance timestamps generally represent candle start times.
    A 15-minute candle is complete after its timestamp plus 15 minutes.
    """

    if data is None or data.empty:
        return pd.DataFrame()

    now_ist = pd.Timestamp.now(tz=IST)

    candle_start_times = _index_in_ist(data)

    candle_end_times = candle_start_times + timedelta(
        minutes=interval_minutes
    )

    completed_mask = candle_end_times <= now_ist

    completed_data = data.loc[completed_mask].copy()

    return completed_data


def _get_latest_session_data(
    completed_data: pd.DataFrame,
) -> tuple[pd.DataFrame, object]:
    """
    Return candles from the latest available trading session.

    This allows the application to work on weekends and market holidays.
    During live market days, it automatically uses the current session.
    """

    if completed_data.empty:
        return pd.DataFrame(), None

    completed_index_ist = _index_in_ist(completed_data)

    session_dates = completed_index_ist.date

    latest_session_date = max(session_dates)

    latest_session_mask = (
        session_dates == latest_session_date
    )

    latest_session_data = completed_data.loc[
        latest_session_mask
    ].copy()

    return latest_session_data, latest_session_date


def prepare_features(symbol: str) -> Optional[dict]:
    """
    Prepare scanner features using completed 15-minute candles.

    The latest available trading session is used when the market is closed.
    Old V6 feature names are preserved for compatibility.
    """

    data = get_intraday_data(
        symbol=symbol,
        period="5d",
        interval="15m",
    )

    if data is None or data.empty:
        return None

    if len(data) < 50:
        return None

    data = data.copy()

    # Exponential moving averages.
    data["EMA20"] = data["Close"].ewm(
        span=20,
        adjust=False,
    ).mean()

    data["EMA50"] = data["Close"].ewm(
        span=50,
        adjust=False,
    ).mean()

    # VWAP and ATR.
    data["VWAP"] = calculate_vwap(data)

    data["ATR"] = calculate_atr(
        data=data,
        period=14,
    )

    # Relative volume.
    data["AVG_VOLUME"] = data["Volume"].rolling(
        window=20,
        min_periods=20,
    ).mean()

    valid_average_volume = data["AVG_VOLUME"].replace(
        0,
        float("nan"),
    )

    data["ROLV"] = (
        data["Volume"] / valid_average_volume
    )

    # Remove rows where indicators are unavailable.
    feature_columns = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "EMA20",
        "EMA50",
        "VWAP",
        "ATR",
        "ROLV",
    ]

    data = data.dropna(
        subset=feature_columns
    ).copy()

    if len(data) < 2:
        return None

    # Use completed candles only.
    completed_data = _completed_candles(
        data=data,
        interval_minutes=15,
    )

    if len(completed_data) < 2:
        return None

    # Use today's session when available.
    # Otherwise use the latest available session.
    session_data, session_date = _get_latest_session_data(
        completed_data
    )

    if session_data.empty:
        return None

    completed = completed_data.iloc[-1]
    previous = completed_data.iloc[-2]

    try:
        live_price = float(data["Close"].iloc[-1])

        completed_open = float(completed["Open"])
        completed_high = float(completed["High"])
        completed_low = float(completed["Low"])
        completed_close = float(completed["Close"])

        previous_close = float(previous["Close"])

        ema20 = float(completed["EMA20"])
        ema50 = float(completed["EMA50"])
        vwap = float(completed["VWAP"])
        atr = float(completed["ATR"])
        rolv = float(completed["ROLV"])

        session_high = float(session_data["High"].max())
        session_low = float(session_data["Low"].min())

    except (ValueError, TypeError, IndexError, KeyError):
        return None

    if any(
        pd.isna(value)
        for value in [
            live_price,
            completed_open,
            completed_high,
            completed_low,
            completed_close,
            previous_close,
            ema20,
            ema50,
            vwap,
            atr,
            rolv,
            session_high,
            session_low,
        ]
    ):
        return None

    current_date = pd.Timestamp.now(
        tz=IST
    ).date()

    is_current_session = (
        session_date == current_date
    )

    return {
        # Basic information.
        "symbol": symbol,
        "session_date": session_date,
        "is_current_session": is_current_session,

        # Dataframes.
        "data": data,
        "completed_data": completed_data,
        "today_data": session_data,
        "session_data": session_data,

        # Latest price and completed candle.
        "live_price": round(live_price, 2),
        "completed_time": completed_data.index[-1],

        "completed_open": completed_open,
        "completed_high": completed_high,
        "completed_low": completed_low,
        "completed_close": completed_close,
        "previous_close": previous_close,

        # Indicators.
        "ema20": ema20,
        "ema50": ema50,
        "vwap": vwap,
        "atr": atr,
        "rolv": rolv,

        # Latest trading-session range.
        "today_high": session_high,
        "today_low": session_low,

        # Full completed-candle history for the latest session.
        # execution.py uses this to reconstruct missed triggers after
        # refreshes, restarts or temporary data outages.
        "session_candles": [
            {
                "time": (
                    pd.Timestamp(index).tz_localize(IST)
                    if pd.Timestamp(index).tzinfo is None
                    else pd.Timestamp(index).tz_convert(IST)
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
            }
            for index, row in session_data.iterrows()
        ],

        # V6 compatibility fields.
        "cmp": round(live_price, 2),
        "latest_high": completed_high,
        "latest_low": completed_low,
        "latest_close": completed_close,
        "prev_close": previous_close,
    }