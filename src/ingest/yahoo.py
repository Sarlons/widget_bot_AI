"""Live equity proxies for PAPER TRADING only: US-listed country ETFs, monthly, from Yahoo.

The research data for country equities (French international indexes) are updated once
a year, so they cannot drive a live monthly decision. For paper trading the same markets
are tracked with iShares MSCI country ETFs (and SPY for the US), in USD:

  yh_{CC} = monthly total return from the dividend-adjusted close (decimal)

Yahoo's chart endpoint is unofficial and adjusted closes are revised after dividends, so
these series are a convenience source: never used in backtests or the holdout. Only
completed months are stored. Lag 0 (month-end close).

Run:  .venv\\Scripts\\python -m src.ingest.yahoo
"""
from __future__ import annotations

import json

import pandas as pd

from src.ingest.download import fetch
from src.ingest.store import append_records, month_end, now_utc, save_raw

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?period1=0&period2=9999999999&interval=1mo"
TICKERS = {"US": "SPY", "DE": "EWG", "FR": "EWQ", "IT": "EWI", "ES": "EWP", "NL": "EWN",
           "CH": "EWL", "GB": "EWU", "JP": "EWJ", "CA": "EWC", "AU": "EWA"}


def parse(cc: str, content: bytes) -> pd.DataFrame:
    r = json.loads(content)["chart"]["result"][0]
    ts = pd.to_datetime(r["timestamp"], unit="s")
    px = pd.Series(r["indicators"]["adjclose"][0]["adjclose"], index=ts, dtype=float)
    # monthly bars are labelled by the first day of the month; keep completed months only
    px = px[ts.to_period("M") < pd.Timestamp.today().to_period("M")]
    px = px.groupby(px.index.to_period("M")).last().dropna()
    ret = px.pct_change().dropna()
    obs = month_end(ret.index.to_timestamp())
    return pd.DataFrame({"series": f"yh_{cc}", "observation_date": obs,
                         "availability_date": obs, "value": ret.to_numpy()})


def ingest() -> int:
    ts = now_utc()
    added = 0
    for cc, t in TICKERS.items():
        content = fetch(URL.format(t=t))
        save_raw("yahoo", f"{t}.json", content, ts)
        added += append_records("yahoo", parse(cc, content), ts)
    return added


if __name__ == "__main__":
    print(f"yahoo: {ingest()} new records")
