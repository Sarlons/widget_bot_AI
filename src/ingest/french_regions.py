"""Kenneth French regional market factors (project 2), monthly, USD, since 1989/1990.

  frg_DEV  developed-markets total return (Mkt-RF + RF): free proxy for MSCI World, 1990-07
  frg_EM   emerging-markets total return (Mkt-RF + RF), 1989-07

Value-weighted, dividends included, from month-end prices. Lag 0 (as french.py).
-99.99 means missing.

Run:  .venv\\Scripts\\python -m src.ingest.french_regions
"""
from __future__ import annotations

import io
import zipfile

import numpy as np
import pandas as pd

from src.ingest.download import fetch
from src.ingest.store import append_records, month_end, now_utc, save_raw

BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FILES = {"frg_DEV": "Developed_3_Factors_CSV.zip", "frg_EM": "Emerging_5_Factors_CSV.zip"}


def parse(name: str, content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        text = z.read(z.namelist()[0]).decode("latin-1")
    rows, header = [], None
    for line in text.splitlines():
        parts = [x.strip() for x in line.split(",")]
        if parts[:2] == ["", "Mkt-RF"]:
            if header is not None:  # second table = annual: stop
                break
            header = parts
            continue
        if header and len(parts[0]) == 6 and parts[0].isdigit():
            rows.append(parts)
    df = pd.DataFrame(rows, columns=header)
    mkt = pd.to_numeric(df["Mkt-RF"]).replace(-99.99, np.nan)
    rf = pd.to_numeric(df["RF"]).replace(-99.99, np.nan)
    obs = month_end(pd.to_datetime(df[""], format="%Y%m"))
    return pd.DataFrame({"series": name, "observation_date": obs, "availability_date": obs,
                         "value": ((mkt + rf) / 100.0).to_numpy()})


def ingest() -> int:
    ts = now_utc()
    added = 0
    for name, f in FILES.items():
        content = fetch(BASE + f)
        save_raw("french_regions", f, content, ts)
        added += append_records("french_regions", parse(name, content), ts)
    return added


if __name__ == "__main__":
    print(f"french_regions: {ingest()} new records")
