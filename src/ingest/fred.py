"""FRED (Federal Reserve Bank of St. Louis) series, via the free CSV endpoint (no API key).

Series and publication lags (months after the observation month ends):
  TB3MS     3-month T-bill rate, monthly average           lag 0   (1934+)
  GS10      10-year Treasury yield, monthly average        lag 0   (1953+)
  CPIAUCSL  CPI, all urban consumers, seasonally adjusted  lag 1   (1947+) released mid next month
  UNRATE    Unemployment rate                              lag 1   (1948+) released 1st Friday next month
  BAA, AAA  Moody's corporate bond yields, monthly average lag 0   (1919+) credit spread = BAA - AAA
  DEXUSEU   USD per EUR, daily -> month-end value          lag 0   (1999+)
  CCUSMA02DEM618N  OECD: EUR per USD for Germany (DEM converted at the fixed 1.95583),
                   monthly average                         lag 0   (1957+), EUR proxy before 1999

Rates are stored as decimals (5.0% -> 0.05). CPI/UNRATE values are today's revised
numbers (revisions not captured; see store.py).

Run:  .venv\\Scripts\\python -m src.ingest.fred
"""
from __future__ import annotations

import io

import pandas as pd

from src.ingest.download import fetch
from src.ingest.store import add_months, append_records, month_end, now_utc, save_raw

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"

# series id -> (lag in months, is a percentage rate, is daily)
SERIES = {
    "TB3MS": (0, True, False),
    "GS10": (0, True, False),
    "CPIAUCSL": (1, False, False),
    "UNRATE": (1, True, False),
    "BAA": (0, True, False),
    "AAA": (0, True, False),
    "DEXUSEU": (0, False, True),
    "CCUSMA02DEM618N": (0, False, False),
}


def parse(sid: str, content: bytes) -> pd.DataFrame:
    lag, is_pct, is_daily = SERIES[sid]
    df = pd.read_csv(io.BytesIO(content))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")  # FRED uses "." for missing
    df = df.dropna()
    if is_daily:
        # month-end value = last available daily observation of each COMPLETED month
        df = df[df["date"].dt.to_period("M") < pd.Timestamp.today().to_period("M")]
        df = df.groupby(df["date"].dt.to_period("M")).last()
    obs = month_end(df["date"])
    value = df["value"].to_numpy(dtype=float)
    if is_pct:
        value = value / 100.0
    return pd.DataFrame({
        "series": f"fred_{sid}",
        "observation_date": obs,
        "availability_date": add_months(obs, lag),
        "value": value,
    })


def ingest() -> int:
    ts = now_utc()
    added = 0
    for sid in SERIES:
        content = fetch(URL.format(sid=sid))
        save_raw("fred", f"{sid}.csv", content, ts)
        added += append_records("fred", parse(sid, content), ts)
    return added


if __name__ == "__main__":
    print(f"fred: {ingest()} new records")
