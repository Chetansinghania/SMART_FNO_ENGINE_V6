import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from scanner.universe import load_universe
from scanner.engine import scan_market

# ==========================
# CONFIGURATION
# ==========================

IST = ZoneInfo("Asia/Kolkata")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCK_FILE = os.path.join(BASE_DIR, "locked_top3.csv")

LOCK_TIME = time(9, 45)

st.set_page_config(
    page_title="SMART F&O ENGINE V6",
    layout="wide"
)

st.title("SMART F&O ENGINE V6 - LOCKED TOP 3")
st.caption("VERSION : V6.2 STABLE")
st.write("Indian Time :", datetime.now(IST).strftime("%d-%m-%Y %H:%M:%S"))

# ==========================
# DATE FUNCTIONS
# ==========================

def today_date():
    return datetime.now(IST).date()


def today_str():
    return datetime.now(IST).strftime("%d-%m-%Y")


# ==========================
# LOAD LOCK FILE
# ==========================

def load_locked_top3():

    if not os.path.exists(LOCK_FILE):
        return None

    try:

        df = pd.read_csv(LOCK_FILE)

        if df.empty:
            return None

        if "date" not in df.columns:
            return None

        df["date"] = pd.to_datetime(
            df["date"],
            format="%d-%m-%Y",
            errors="coerce"
        ).dt.date

        today_df = df[df["date"] == today_date()].copy()

        if today_df.empty:
            return None

        today_df.drop(columns=["date"], inplace=True)

        return today_df

    except Exception as e:

        st.error(f"Lock file error : {e}")

        return None


# ==========================
# SAVE LOCK FILE
# ==========================

def save_locked_top3(results):

    df = pd.DataFrame(results)

    if df.empty:
        return

    df.insert(0, "date", today_str())

    df.to_csv(LOCK_FILE, index=False)


# ==========================
# SCANNER
# ==========================

@st.cache_data(ttl=300)
def cached_scan():

    stocks = load_universe()

    return scan_market(stocks)


# ==========================
# REFRESH
# ==========================

if st.button("Refresh Scanner"):

    st.cache_data.clear()

    st.rerun()


# ==========================
# MAIN LOGIC
# ==========================

locked_df = load_locked_top3()

if locked_df is not None:

    df = locked_df.copy()

    st.success("Today's Top 3 already locked.")

else:

    results = cached_scan()

    if len(results) == 0:

        st.warning("No high quality setup found.")

        st.stop()

    now = datetime.now(IST).time()

    if now >= LOCK_TIME:

        save_locked_top3(results)

        df = pd.DataFrame(results)

        st.success("Today's Top 3 locked successfully.")

    else:

        df = pd.DataFrame(results)

        st.warning("Observation Mode (Before 09:45 AM)")


# ==========================
# DISPLAY
# ==========================

if "_score" in df.columns:
    df.drop(columns=["_score"], inplace=True)

if "Rank" in df.columns:
    df.drop(columns=["Rank"], inplace=True)

df.insert(0, "Rank", range(1, len(df)+1))

st.subheader("TOP 3 TRADES")

st.dataframe(df, use_container_width=True)

st.info(
    """
After 09:45 AM (IST), the Top 3 trades are locked for the trading day.

The scanner will continue refreshing market data,
but today's locked trades remain unchanged.
"""
)