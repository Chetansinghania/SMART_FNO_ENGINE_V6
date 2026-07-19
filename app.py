import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from scanner.engine import scan_market
from scanner.execution import monitor_watchlist
from scanner.universe import load_universe


# ==========================
# CONFIGURATION
# ==========================

IST = ZoneInfo("Asia/Kolkata")

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

LOCK_FILE = os.path.join(
    BASE_DIR,
    "locked_top2.csv",
)

BACKTEST_FILE = os.path.join(
    BASE_DIR,
    "backtest_results.csv",
)

LOCK_TIME = time(9, 45)


st.set_page_config(
    page_title="SMART F&O ENGINE V7",
    layout="wide",
)

st.title("SMART F&O ENGINE V7 - LOCKED TOP 2")
st.caption("VERSION: V7.5 ONE-MONTH BACKTEST MODE")

st.write(
    "Indian Time:",
    datetime.now(IST).strftime(
        "%d-%m-%Y %H:%M:%S"
    ),
)


# ==========================
# DATE FUNCTIONS
# ==========================

def today_date():
    """Return the current Indian date."""

    return datetime.now(IST).date()


def today_str():
    """Return the current Indian date as text."""

    return datetime.now(IST).strftime(
        "%d-%m-%Y"
    )


def now_str():
    """Return the current Indian date and time."""

    return datetime.now(IST).strftime(
        "%d-%m-%Y %H:%M:%S"
    )


# ==========================
# WATCHLIST STORAGE
# ==========================

def load_locked_top2():
    """Load today's locked Top 2 watchlist."""

    if not os.path.exists(LOCK_FILE):
        return None

    try:
        dataframe = pd.read_csv(LOCK_FILE)

        if dataframe.empty or "date" not in dataframe.columns:
            return None

        dataframe["date"] = pd.to_datetime(
            dataframe["date"],
            format="%d-%m-%Y",
            errors="coerce",
        ).dt.date

        today_dataframe = dataframe[
            dataframe["date"] == today_date()
        ].copy()

        if today_dataframe.empty:
            return None

        today_dataframe.drop(
            columns=["date"],
            inplace=True,
        )

        return today_dataframe

    except Exception as exc:
        st.error(
            f"Watchlist lock file error: {exc}"
        )
        return None


def save_locked_top2(results):
    """Save today's Top 2 watchlist."""

    dataframe = pd.DataFrame(results)

    if dataframe.empty:
        return False

    dataframe.insert(
        0,
        "date",
        today_str(),
    )

    try:
        dataframe.to_csv(
            LOCK_FILE,
            index=False,
        )
        return True

    except Exception as exc:
        st.error(
            f"Unable to save watchlist: {exc}"
        )
        return False


# ==========================
# BACKTEST JOURNAL
# ==========================

def save_backtest_snapshot(dataframe):
    """
    Save one row per meaningful stock-status update.

    Internal Score, ROLV, Reason and trigger-distance fields are not
    written to the visible dashboard. The journal keeps only practical
    trade-review fields.
    """

    if dataframe is None or dataframe.empty:
        return

    journal_columns = [
        "Stock",
        "Action",
        "Status",
        "CMP",
        "Trigger Price",
        "Entry",
        "SL",
        "Target 1",
        "Target 2",
        "Triggered At",
        "Last Updated",
    ]

    snapshot = dataframe.copy()

    for column in journal_columns:
        if column not in snapshot.columns:
            snapshot[column] = None

    snapshot = snapshot[journal_columns].copy()
    snapshot.insert(0, "Recorded At", now_str())
    snapshot.insert(0, "Date", today_str())

    try:
        if os.path.exists(BACKTEST_FILE):
            existing = pd.read_csv(BACKTEST_FILE)

            combined = pd.concat(
                [existing, snapshot],
                ignore_index=True,
            )

            dedupe_columns = [
                "Date",
                "Stock",
                "Status",
                "CMP",
                "Last Updated",
            ]

            combined.drop_duplicates(
                subset=dedupe_columns,
                keep="last",
                inplace=True,
            )
        else:
            combined = snapshot

        combined.to_csv(
            BACKTEST_FILE,
            index=False,
        )

    except Exception as exc:
        st.warning(
            f"Backtest journal could not be updated: {exc}"
        )


# ==========================
# SCANNER
# ==========================

@st.cache_data(ttl=300)
def cached_scan():
    """Run the internal stock-selection scanner."""

    stocks = load_universe()
    return scan_market(stocks)


# ==========================
# MANUAL REFRESH
# ==========================

if st.button("Refresh Scanner and Monitor"):
    st.cache_data.clear()
    st.rerun()


# ==========================
# MAIN WORKFLOW
# ==========================

locked_dataframe = load_locked_top2()
is_locked = locked_dataframe is not None

if is_locked:
    watchlist_dataframe = locked_dataframe.copy()

    st.success(
        "Today's Top 2 watchlist is already locked."
    )

else:
    results = cached_scan()

    if not results:
        st.warning(
            "No high-quality watchlist candidate found."
        )
        st.stop()

    current_time = datetime.now(IST).time()
    watchlist_dataframe = pd.DataFrame(results)

    if current_time >= LOCK_TIME:
        saved = save_locked_top2(results)

        if saved:
            is_locked = True
            st.success(
                "Today's Top 2 watchlist locked successfully."
            )
        else:
            st.error(
                "The watchlist could not be locked. "
                "Execution monitoring has not started."
            )

    else:
        st.warning(
            "Observation mode before 09:45 AM IST. "
            "The watchlist is not locked yet."
        )


# ==========================
# EXECUTION MONITORING
# ==========================

if is_locked:
    execution_rows = monitor_watchlist(
        watchlist_dataframe
    )

    if execution_rows:
        display_dataframe = pd.DataFrame(
            execution_rows
        )
    else:
        display_dataframe = watchlist_dataframe.copy()
        st.warning(
            "The watchlist is locked, but execution data "
            "is currently unavailable."
        )
else:
    display_dataframe = watchlist_dataframe.copy()

    if "Status" not in display_dataframe.columns:
        display_dataframe["Status"] = "WAITING"


# Save a clean historical record for the one-month backtest.
save_backtest_snapshot(display_dataframe)


# ==========================
# FORMAT COLUMNS
# ==========================

numeric_columns = [
    "CMP",
    "Trigger Price",
    "Entry",
    "SL",
    "Target 1",
    "Target 2",
    "Progress %",
]

for column in numeric_columns:
    if column in display_dataframe.columns:
        display_dataframe[column] = pd.to_numeric(
            display_dataframe[column],
            errors="coerce",
        ).round(2)


# ==========================
# SUMMARY METRICS
# ==========================

status_series = display_dataframe.get(
    "Status",
    pd.Series(dtype=str),
).astype(str)

ready_count = int(
    status_series.isin(
        ["READY", "WAITING"]
    ).sum()
)

active_count = int(
    status_series.isin(
        ["TRIGGERED", "ACTIVE", "TARGET 1 HIT"]
    ).sum()
)

completed_count = int(
    status_series.isin(
        ["TARGET 2 HIT", "STOP LOSS HIT"]
    ).sum()
)

metric_1, metric_2, metric_3 = st.columns(3)

metric_1.metric(
    "Waiting / Ready",
    ready_count,
)

metric_2.metric(
    "Active Trades",
    active_count,
)

metric_3.metric(
    "Completed Trades",
    completed_count,
)


# ==========================
# MINIMAL WATCHLIST DISPLAY
# ==========================

watchlist_columns = [
    "Rank",
    "Stock",
    "Action",
    "CMP",
    "Status",
    "Trigger Price",
    "Last Updated",
]

available_watchlist_columns = [
    column
    for column in watchlist_columns
    if column in display_dataframe.columns
]

st.subheader("TODAY'S LOCKED WATCHLIST")

st.dataframe(
    display_dataframe[
        available_watchlist_columns
    ],
    use_container_width=True,
    hide_index=True,
)


# ==========================
# TRADE LIFECYCLE
# ==========================

trade_statuses = [
    "TRIGGERED",
    "ACTIVE",
    "TARGET 1 HIT",
    "TARGET 2 HIT",
    "STOP LOSS HIT",
]

if "Status" in display_dataframe.columns:
    trade_dataframe = display_dataframe[
        display_dataframe["Status"].isin(
            trade_statuses
        )
    ].copy()
else:
    trade_dataframe = pd.DataFrame()

if not trade_dataframe.empty:
    trade_columns = [
        "Stock",
        "Action",
        "Status",
        "CMP",
        "Entry",
        "SL",
        "Target 1",
        "Target 2",
        "Progress %",
        "Triggered At",
        "Last Updated",
    ]

    available_trade_columns = [
        column
        for column in trade_columns
        if column in trade_dataframe.columns
    ]

    st.subheader("TRADE LIFECYCLE")

    st.dataframe(
        trade_dataframe[
            available_trade_columns
        ],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info(
        "No trade has triggered yet. Entry, stop-loss and "
        "targets will appear only after a valid breakout."
    )


st.info(
    """
One-month backtest mode is active.

Score, ROLV, trigger distance and execution reasons are calculated
internally but hidden from the dashboard.

Every refresh records the practical trade data in backtest_results.csv.
Do not change the strategy settings during the testing period.
"""
)

st.caption(
    "Market data from free sources may be delayed. "
    "Use this system for backtesting and paper-trading evaluation."
)
