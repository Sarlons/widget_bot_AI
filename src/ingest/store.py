"""Point-in-time data store.

Two layers:

1. data/raw/<source>/<timestamp>_<name>   -- downloaded files, saved byte-for-byte,
   never modified or overwritten (each download gets a new timestamped file).
2. data/pit/<source>.parquet              -- the same data parsed into "long" records:

       series | observation_date | availability_date | value | download_ts

   observation_date  = the period the number refers to (month-end).
   availability_date = the first date an investor could have known it
                       (observation_date + publication lag, see docs/data_lags.md).
   download_ts       = when we downloaded it (to keep different vintages apart).

   The file is append-only: new downloads add rows, old rows are never deleted.
   Exact duplicates (same series, dates and value) are not stored twice.

The ONLY way models should read data is `as_of(T)`: it returns what was known at date T.

Limitation: free sources give today's (revised) numbers, not the numbers originally
published. Publication lags are respected, but data revisions (e.g. CPI, unemployment)
are not. ALFRED (FRED's vintage archive) could fix this later.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PIT_DIR = ROOT / "data" / "pit"
COLUMNS = ["series", "observation_date", "availability_date", "value", "download_ts"]


def now_utc() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None).floor("s")


def save_raw(source: str, name: str, content: bytes, ts: pd.Timestamp | None = None) -> Path:
    """Save downloaded bytes unmodified under a new timestamped filename."""
    ts = ts or now_utc()
    folder = RAW_DIR / source
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{ts:%Y%m%dT%H%M%S}_{name}"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite raw file {path}")
    path.write_bytes(content)
    return path


def append_records(source: str, records: pd.DataFrame, download_ts: pd.Timestamp,
                   pit_dir: Path = PIT_DIR) -> int:
    """Append parsed records (series, observation_date, availability_date, value).

    Returns the number of new rows actually added.
    """
    missing = {"series", "observation_date", "availability_date", "value"} - set(records.columns)
    if missing:
        raise ValueError(f"records missing columns {missing}")
    new = records.copy()
    new["download_ts"] = download_ts
    new = new.dropna(subset=["value"])[COLUMNS]
    new["observation_date"] = pd.to_datetime(new["observation_date"])
    new["availability_date"] = pd.to_datetime(new["availability_date"])
    if (new["availability_date"] < new["observation_date"]).any():
        raise ValueError("availability_date earlier than observation_date")

    pit_dir.mkdir(parents=True, exist_ok=True)
    path = pit_dir / f"{source}.parquet"
    if path.exists():
        old = pd.read_parquet(path)
        key = ["series", "observation_date", "availability_date", "value"]
        merged = new.merge(old[key].drop_duplicates(), on=key, how="left", indicator=True)
        new = merged.loc[merged["_merge"] == "left_only", COLUMNS]
        combined = pd.concat([old, new], ignore_index=True)
    else:
        combined = new
    combined.to_parquet(path, index=False)
    return len(new)


def load_all(pit_dir: Path = PIT_DIR) -> pd.DataFrame:
    """All records from every source, long format."""
    files = sorted(pit_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no data in {pit_dir}; run: python -m src.ingest.run_all")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def as_of(records: pd.DataFrame, T, series: list[str] | None = None) -> pd.DataFrame:
    """What an investor could know at date T, as a wide table.

    Keeps rows with availability_date <= T; if a value exists in several vintages,
    the most recently downloaded one is used. Returns a DataFrame indexed by
    observation_date (month-end) with one column per series.
    """
    T = pd.Timestamp(T)
    r = records[records["availability_date"] <= T]
    if series is not None:
        r = r[r["series"].isin(series)]
    r = r.sort_values("download_ts").drop_duplicates(["series", "observation_date"], keep="last")
    wide = r.pivot(index="observation_date", columns="series", values="value").sort_index()
    wide.columns.name = None
    if series is not None:
        wide = wide.reindex(columns=series)
    return wide


def month_end(dates) -> pd.DatetimeIndex:
    """Map any dates to the last calendar day of their month."""
    return pd.DatetimeIndex(pd.to_datetime(dates)).to_period("M").to_timestamp(how="end").normalize()


def add_months(dates: pd.DatetimeIndex, months) -> pd.DatetimeIndex:
    """Shift month-end dates forward by `months` (scalar or array), keeping month-end."""
    p = pd.DatetimeIndex(dates).to_period("M")
    months = np.broadcast_to(np.asarray(months, dtype=int), (len(p),))
    shifted = pd.PeriodIndex([d + int(m) for d, m in zip(p, months)], freq="M")
    return shifted.to_timestamp(how="end").normalize()
