import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
FNO_FILE = os.path.join(BASE_DIR, "data", "fno_stocks.csv")


def load_universe():
    try:
        df = pd.read_csv(FNO_FILE)

        if "symbol" not in df.columns:
            print("CSV must have column name: symbol")
            return []

        symbols = (
            df["symbol"]
            .dropna()
            .astype(str)
            .str.strip()
            .tolist()
        )

        return symbols

    except Exception as e:
        print("Universe file error:", e)
        return []