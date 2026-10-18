"""Kenneth French data library: Fama-French 3 factors, monthly (since 1926-07).

  ff_MKT_RF  US market (CRSP value-weighted, all NYSE/AMEX/NASDAQ) return minus T-bill
  ff_SMB     size factor,  ff_HML  value factor
  ff_RF      1-month T-bill return

Market + RF is our total-return proxy for the S&P 500 (correlation ~0.99): it is based
on month-END prices, whereas Shiller's S&P prices are monthly AVERAGES, which create
artificial autocorrelation and would flatter trend rules.

Lag 0: returns are computed from prices observable at month end. (French publishes the
file with a 1-2 month delay, but the underlying market data were public.)
Values are converted from percent to decimals.

Run:  .venv\\Scripts\\python -m src.ingest.french
"""
from __future__ import annotations

import io
import zipfile

import pandas as pd

from src.ingest.download import fetch
from src.ingest.store import append_records, month_end, now_utc, save_raw

URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip"
NAMES = {"Mkt-RF": "ff_MKT_RF", "SMB": "ff_SMB", "HML": "ff_HML", "RF": "ff_RF"}


def parse(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        text = z.read(z.namelist()[0]).decode("latin-1")
    # The CSV has a text header, a monthly block (YYYYMM rows), then an annual block.
    rows, header = [], None
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if header is None and len(parts) > 1 and parts[1] == "Mkt-RF":
            header = parts[1:]
            continue
        if header is not None:
            if len(parts[0]) == 6 and parts[0].isdigit():
                rows.append(parts)
            elif rows:  # first non-monthly line after the block: stop
                break
    df = pd.DataFrame(rows, columns=["yyyymm"] + header)
    obs = month_end(pd.to_datetime(df["yyyymm"], format="%Y%m"))
    out = []
    for col, name in NAMES.items():
        out.append(pd.DataFrame({
            "series": name,
            "observation_date": obs,
            "availability_date": obs,
            "value": pd.to_numeric(df[col]).to_numpy(dtype=float) / 100.0,
        }))
    return pd.concat(out, ignore_index=True)


def ingest() -> int:
    content = fetch(URL)
    ts = now_utc()
    save_raw("french", "F-F_Research_Data_Factors_CSV.zip", content, ts)
    return append_records("french", parse(content), ts)


if __name__ == "__main__":
    print(f"french: {ingest()} new records")
