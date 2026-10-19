"""Kenneth French international country indexes (since 1975), monthly.

From F-F_International_Countries.zip we use, for each country file, the first table
"Value-Weight Dollar Returns" column "Mkt": the value-weighted total return (dividends
included) of that country's stock market, in USD. Stored as ffi_<COUNTRY> (decimal).
-99.99 means missing.

Lag 0: returns from month-end prices that were public at the time. (French updates the
file once a year, but the underlying market data were observable.)

Run:  .venv\\Scripts\\python -m src.ingest.french_intl
"""
from __future__ import annotations

import io
import zipfile

import numpy as np
import pandas as pd

from src.ingest.download import fetch
from src.ingest.store import append_records, month_end, now_utc, save_raw

URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_International_Countries.zip"
# file name in the zip -> our country code (same codes as the FRED/OECD series)
COUNTRIES = {"Germany.Dat": "DE", "France.Dat": "FR", "Italy.Dat": "IT", "Spain.Dat": "ES",
             "Nethrlnd.Dat": "NL", "Swtzrlnd.Dat": "CH", "UK.Dat": "GB", "Japan.Dat": "JP",
             "Canada.Dat": "CA", "Austrlia.Dat": "AU",
             # project 2 (docs/globalrank_preregistration.md): the remaining countries
             "Austria.Dat": "AT", "Belgium.Dat": "BE", "Denmark.Dat": "DK", "Finland.Dat": "FI",
             "HongKong.Dat": "HK", "Ireland.Dat": "IE", "Malaysia.Dat": "MY",
             "NewZland.Dat": "NZ", "Norway.Dat": "NO", "Singapor.Dat": "SG", "Sweden.Dat": "SE"}


def parse_country(text: str) -> pd.Series:
    """First table of a country file -> monthly USD total returns (decimal)."""
    dates, values, in_table = [], [], False
    for line in text.splitlines():
        parts = line.split()
        if parts[:1] == ["Mkt"]:
            in_table = True
            continue
        if in_table:
            if len(parts) > 1 and len(parts[0]) == 6 and parts[0].isdigit():
                dates.append(parts[0])
                values.append(float(parts[1]))
            elif dates:  # blank line after the first table: stop
                break
    s = pd.Series(values, index=month_end(pd.to_datetime(dates, format="%Y%m")))
    return s.replace(-99.99, np.nan) / 100.0


def parse(content: bytes) -> pd.DataFrame:
    out = []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for fname, cc in COUNTRIES.items():
            s = parse_country(z.read(fname).decode("latin-1"))
            out.append(pd.DataFrame({"series": f"ffi_{cc}", "observation_date": s.index,
                                     "availability_date": s.index, "value": s.to_numpy()}))
    return pd.concat(out, ignore_index=True)


def ingest() -> int:
    content = fetch(URL)
    ts = now_utc()
    save_raw("french_intl", "F-F_International_Countries.zip", content, ts)
    return append_records("french_intl", parse(content), ts)


if __name__ == "__main__":
    print(f"french_intl: {ingest()} new records")
