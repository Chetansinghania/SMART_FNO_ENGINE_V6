import streamlit as st
import pandas as pd

from scanner.universe import load_universe
from scanner.engine import scan_market

st.set_page_config(
    page_title="SMART F&O ENGINE V6",
    layout="wide"
)

st.title("SMART F&O ENGINE V6 - TOP 3 TRADES")

if st.button("Refresh Scanner"):
    st.cache_data.clear()
    st.rerun()


@st.cache_data(ttl=300)
def cached_scan():
    stocks = load_universe()
    return scan_market(stocks)


results = cached_scan()

if len(results) == 0:
    st.warning("No high-quality trade setup found right now.")
    st.stop()

df = pd.DataFrame(results)
df.insert(0, "Rank", range(1, len(df) + 1))

st.subheader("TOP TRADES")

st.dataframe(df, use_container_width=True)

st.info(
    "Internal score is calculated but hidden. "
    "Dashboard shows only Stock, Action, Entry, SL, Target 1 and Target 2."
)