"""Walk-forward bookkeeping: evaluation periods, forecast dates, purging and embargo.

Picture for a 12-month label at forecast date T (months on the axis):

    label at t covers returns t+1 ... t+h  -> fully known only at t+h
    usable for training at T only if  t + h + embargo <= T      (purging + embargo)

Purging removes labels whose window overlaps the future; the embargo adds an extra gap
so serial correlation cannot leak information across the boundary.
"""
from __future__ import annotations

import pandas as pd

HOLDOUT_START = pd.Timestamp("2015-01-01")  # locked: never evaluate before the final test
DEV_END = pd.Timestamp("2014-12-31")        # last month-end of the development period


def month_ends(start, end) -> pd.DatetimeIndex:
    return pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="ME")


def assert_no_holdout(dates) -> None:
    """Raise if anything would be evaluated inside the locked holdout."""
    if pd.DatetimeIndex(dates).max() >= HOLDOUT_START:
        raise RuntimeError("attempt to evaluate inside the locked holdout (2015+)")


def last_usable_label(T, horizon: int, embargo: int = 1) -> pd.Timestamp:
    """Latest label date t whose h-month window ended at least `embargo` months before T."""
    return (pd.Timestamp(T).to_period("M") - horizon - embargo).to_timestamp(how="end").normalize()
