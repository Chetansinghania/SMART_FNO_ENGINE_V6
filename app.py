import os
from datetime import datetime, time

import pandas as pd
import streamlit as st

from scanner.universe import load_universe
from scanner.engine import scan_market

LOCK_FILE = "locked_top3.csv"
LOCK_TIME = time(9, 45)

st.set_page_config(
    page_title="SMART F&O ENGINE V6",
    layout="wide"
)

st.title("SMART F&O ENGINE V6 - LOCKED TOP 3")


def today_str():
    return datetime.now().strftime("%Y-%m-%d")


def load_locked_top3():
    if not os.path.exists(LOCK_FILE):
        return None

    df = pd.read_csv(LOCK_FILE)

    today_df = df[df["date"] == today_str()]

    if today_df.empty:
        return None

    return today_df.drop(columns=["date"])


def save_locked_top3(results):
    df = pd.DataFrame(results)

    if df.empty:
        return

    df.insert(0, "date", today_str())
    df.to_csv(LOCK_FILE, index=False)


@st.cache_data(ttl=300)
def cached_scan():
    stocks = load_universe()
    return scan_market(stocks)


if st.button("Refresh Scanner"):
    st.cache_data.clear()
    st.rerun()


locked_df = load_locked_top3()

if locked_df is not None:
    st.success("Top 3 locked for today. Refresh will not replace stocks.")
    df = locked_df.copy()

else:
    results = cached_scan()

    if len(results) == 0:
        st.warning("No high-quality trade setup found right now.")
        st.stop()

    df = pd.DataFrame(results)

    if datetime.now().time() >= LOCK_TIME:
        save_locked_top3(results)
        st.success("Top 3 locked now for today.")
    else:
        st.warning("Observation mode. Top 3 will lock after 09:45 AM.")


df.insert(0, "Rank", range(1, len(df) + 1))

st.subheader("TOP 3 TRADES")

st.dataframe(df, use_container_width=True)

st.info(
    "Before 09:45 AM: Observation mode, list may change. "
    "After 09:45 AM: Top 3 stocks are locked for the day."
)