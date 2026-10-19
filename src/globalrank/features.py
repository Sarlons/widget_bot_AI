"""Price-only features and the 3-month rank label (pre-registration section 4).

    f = features_at(p, T)       # one row per eligible index, ranked features in [0, 1]
    y = label(p, t, eligible)   # percentile rank of the next 3-month return after t

`p` is a panel from data.panel_at(records, T); features_at uses only rows <= T.
An index is eligible at T if it has 36 monthly returns up to T and a return at T.
Missing ranks (e.g. the world correlation before the benchmark has 36 months, 1993-06)
are set to 0.5, the cross-sectional middle.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.globalrank.data import ASSETS

FEATURES = ["r1", "r3", "r6", "r12_1", "dist_high", "vol12", "drawdown", "corr_world", "slope12"]
MIN_MONTHS = 36
HORIZON = 3


def eligible(p: pd.DataFrame, T) -> list[str]:
    h = p.loc[:pd.Timestamp(T)]
    tail = h[ASSETS].iloc[-MIN_MONTHS:]
    return [c for c in ASSETS if len(tail) == MIN_MONTHS and tail[c].notna().all()]


def features_at(p: pd.DataFrame, T) -> pd.DataFrame:
    h = p.loc[:pd.Timestamp(T)]
    cols = eligible(p, T)
    if not cols:
        return pd.DataFrame(columns=FEATURES)
    r = h[cols]
    idx = (1 + r.fillna(0)).cumprod()
    cum = lambda a, b: (1 + r.iloc[len(r) - a:len(r) - b]).prod() - 1  # noqa: E731
    f = pd.DataFrame(index=cols)
    f["r1"] = r.iloc[-1]
    f["r3"] = cum(3, 0)
    f["r6"] = cum(6, 0)
    f["r12_1"] = cum(12, 1)
    f["dist_high"] = idx.iloc[-1] / idx.iloc[-12:].max() - 1
    f["vol12"] = r.iloc[-12:].std()
    f["drawdown"] = idx.iloc[-1] / idx.cummax().iloc[-1] - 1
    w = h["WORLD"].iloc[-MIN_MONTHS:]
    f["corr_world"] = (r.iloc[-MIN_MONTHS:].corrwith(w) if w.notna().all()
                       else pd.Series(np.nan, index=cols))
    x = np.arange(12) - 5.5
    logi = np.log(idx.iloc[-12:].to_numpy())
    f["slope12"] = (x @ (logi - logi.mean(axis=0))) / (x @ x)
    return f.rank(pct=True).fillna(0.5)[FEATURES]


def label(p: pd.DataFrame, t, cols: list[str]) -> pd.Series:
    """Percentile rank of the compounded return of months t+1..t+3 (needs data to t+3)."""
    t = pd.Timestamp(t)
    fut = p.loc[p.index > t, cols].iloc[:HORIZON]
    if len(fut) < HORIZON:
        return pd.Series(np.nan, index=cols)
    return ((1 + fut).prod() - 1).where(fut.notna().all()).rank(pct=True)
