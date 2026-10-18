"""Robert Shiller's monthly US stock market data (since 1871).

Columns used: S&P Composite price P (monthly average of daily closes), dividends D and
earnings E (12-month trailing, per share, index units), CPI, long-term interest rate
(10y Treasury, GS10 after 1953).

Publication lags (availability = month-end of observation + lag, in months):
  P, rate : 0   P and the rate are monthly averages, known at the end of the month.
  CPI     : 1   (15 before 1913: annual Warren-Pearson index, interpolated)
  D, E    : 6   S&P quarterly figures, linearly interpolated by Shiller: a month's value
                depends on the quarter-end figure, reported ~3 months after quarter end.
           15   before 1926: annual Cowles data interpolated, so a month in year Y uses
                the annual figure for year Y, known only in Q1 of year Y+1.
See docs/data_lags.md.

Run:  .venv\\Scripts\\python -m src.ingest.shiller
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

from src.ingest.download import fetch
from src.ingest.store import add_months, append_records, now_utc, save_raw

# shillerdata.com is the current home of the file; Yale is the old (frozen 2023) copy.
URLS = [
    "https://img1.wsimg.com/blobby/go/e5e77e0b-59d1-44d9-ab25-4763ac982e53/downloads/ie_data.xls",
    "http://www.econ.yale.edu/~shiller/data/ie_data.xls",
]
# column position in the 'Data' sheet -> our series name
COLUMNS = {1: "shiller_P", 2: "shiller_D", 3: "shiller_E", 4: "shiller_CPI", 6: "shiller_rate"}


def _lag_months(series: str, obs: pd.DatetimeIndex) -> np.ndarray:
    year = obs.year.to_numpy()
    if series in ("shiller_P", "shiller_rate"):
        return np.zeros(len(obs), dtype=int)
    if series == "shiller_CPI":
        return np.where(year < 1913, 15, 1)
    return np.where(year < 1926, 15, 6)  # D and E


def parse(content: bytes) -> pd.DataFrame:
    """Turn the raw Excel bytes into long point-in-time records."""
    sheet = pd.read_excel(io.BytesIO(content), sheet_name="Data", header=None, skiprows=8)
    date_code = pd.to_numeric(sheet[0], errors="coerce")
    sheet = sheet[date_code.notna()]
    date_code = date_code[date_code.notna()]
    # Dates are coded as year.month floats: 1871.01 = Jan, 1871.1 = Oct (not Jan!)
    year = np.floor(date_code).astype(int)
    month = np.round((date_code - year) * 100).astype(int)
    obs = pd.DatetimeIndex(pd.to_datetime(dict(year=year, month=month, day=1))) \
        .to_period("M").to_timestamp(how="end").normalize()

    out = []
    for col, name in COLUMNS.items():
        values = pd.to_numeric(sheet[col], errors="coerce").to_numpy(dtype=float)
        if name == "shiller_rate":
            values = values / 100.0  # percent -> decimal
        out.append(pd.DataFrame({
            "series": name,
            "observation_date": obs,
            "availability_date": add_months(obs, _lag_months(name, obs)),
            "value": values,
        }))
    return pd.concat(out, ignore_index=True).dropna(subset=["value"])


def ingest() -> int:
    last_err = None
    for url in URLS:
        try:
            content = fetch(url)
            break
        except Exception as e:  # try the next mirror
            last_err = e
    else:
        raise RuntimeError(f"Shiller download failed: {last_err}")
    ts = now_utc()
    save_raw("shiller", "ie_data.xls", content, ts)
    return append_records("shiller", parse(content), ts)


if __name__ == "__main__":
    print(f"shiller: {ingest()} new records")
