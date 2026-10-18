"""World Bank commodity prices (the "Pink Sheet"), monthly averages in USD, since 1960.

We keep only gold (USD per troy ounce) as `wb_GOLD` (pre-registration amendment C).
Prices are MONTHLY AVERAGES of daily prices, so returns are smoothed; gold's trend
signals therefore skip the most recent month (see docs/preregistration.md, section 11).

Lag 1: the Pink Sheet is published in the first days of the following month.

Run:  .venv\\Scripts\\python -m src.ingest.worldbank
"""
from __future__ import annotations

import io

import pandas as pd

from src.ingest.download import fetch
from src.ingest.store import add_months, append_records, month_end, now_utc, save_raw

URL = ("https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/"
       "related/CMO-Historical-Data-Monthly.xlsx")
COLUMNS = {"Gold": "wb_GOLD"}
LAG = 1


def parse(content: bytes) -> pd.DataFrame:
    d = pd.read_excel(io.BytesIO(content), sheet_name="Monthly Prices", header=4)
    d = d.rename(columns={d.columns[0]: "month"})
    d = d[d["month"].astype(str).str.fullmatch(r"\d{4}M\d{2}")]
    obs = month_end(pd.to_datetime(d["month"].str.replace("M", "-")))
    out = []
    for col, name in COLUMNS.items():
        v = pd.to_numeric(d[col], errors="coerce").to_numpy(dtype=float)
        out.append(pd.DataFrame({"series": name, "observation_date": obs,
                                 "availability_date": add_months(obs, LAG), "value": v}))
    return pd.concat(out, ignore_index=True)


def ingest() -> int:
    content = fetch(URL)
    ts = now_utc()
    save_raw("worldbank", "CMO-Historical-Data-Monthly.xlsx", content, ts)
    return append_records("worldbank", parse(content), ts)


if __name__ == "__main__":
    print(f"worldbank: {ingest()} new records")
