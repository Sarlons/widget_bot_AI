"""US CAPE (Shiller P/E10) as it was known at each date, for the valuation overlay E.

    cape_percentile(records, T) -> float   # percentile of CAPE at T in its history up to T

CAPE at month t = real price at t / average real earnings of the last 120 months whose
earnings were already published at t. Real = deflated by CPI (each earnings figure by the
CPI of its own month; the price by the latest CPI published at t).

The history used for the percentile is itself point-in-time: the CAPE of a past month t
uses only data available at t (earnings lag 6 months, 15 before 1926; CPI lag 1, 15
before 1913), so the comparison never uses data published later.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SERIES = ["shiller_P", "shiller_E", "shiller_CPI"]
WINDOW = 120
START = pd.Timestamp("1881-01-31")


def latest_known(records: pd.DataFrame, series: str, values: pd.Series,
                 dates: pd.DatetimeIndex) -> pd.Series:
    """For each date t, `values` at the latest observation of `series` available by t."""
    r = records[records["series"] == series]
    avail = r.groupby("observation_date")["availability_date"].min().sort_index()
    # latest observation date available at t: running max of obs over availability order
    by_avail = pd.Series(avail.index, index=avail.to_numpy()).sort_index().cummax()
    by_avail = by_avail.groupby(level=0).max()
    last_obs = by_avail.reindex(by_avail.index.union(dates)).ffill().reindex(dates)
    return pd.Series(values.reindex(last_obs.to_numpy()).to_numpy(), index=dates)


def cape_history(records: pd.DataFrame, T) -> pd.Series:
    """Point-in-time CAPE for every month-end from 1881 to T, using records available at T."""
    T = pd.Timestamp(T)
    r = records[(records["availability_date"] <= T) & records["series"].isin(SERIES)]
    r = r.sort_values("download_ts").drop_duplicates(["series", "observation_date"], keep="last")
    w = r.pivot(index="observation_date", columns="series", values="value").sort_index()
    real_e = (w["shiller_E"] / w["shiller_CPI"]).dropna()
    avg_e = real_e.rolling(WINDOW, min_periods=WINDOW).mean()
    dates = w.index[(w.index >= START) & (w.index <= T)]
    cpi_t = latest_known(r, "shiller_CPI", w["shiller_CPI"], dates)
    e_t = latest_known(r, "shiller_E", avg_e, dates)
    return (w["shiller_P"].reindex(dates) / cpi_t / e_t).dropna()


def cape_percentile(records: pd.DataFrame, T) -> float:
    """Share of past CAPE readings (up to T) that are <= the CAPE at T."""
    h = cape_history(records, T)
    if h.empty:
        return np.nan
    return float((h <= h.iloc[-1]).mean())
