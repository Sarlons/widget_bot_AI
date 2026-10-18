"""Baseline forecast: the prevailing (expanding) historical mean of the label.

Label (pre-registered): fwd_ret_h at month t = sum of monthly log excess returns of
equity over T-bills in months t+1 ... t+h (USD, so forecasts are currency-neutral).

At forecast date T the model averages every label already fully observed, respecting
purging and embargo. Goyal & Welch (2008) showed this "boring" forecast is very hard to
beat out of sample; every later model is scored against it (OOS R2, Clark-West).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.validation.walkforward import last_usable_label


def log_excess(panel: pd.DataFrame) -> pd.Series:
    return np.log1p(panel["eq_usd"]) - np.log1p(panel["rf_usd"])


def forward_label(panel: pd.DataFrame, horizon: int) -> pd.Series:
    """fwd_ret_h indexed by the label date t (NaN where the window is not complete)."""
    x = log_excess(panel)
    return x[::-1].rolling(horizon).sum()[::-1].shift(-1)


def forecast(panel: pd.DataFrame, T, horizon: int, embargo: int = 1) -> float:
    """Expanding-mean forecast of fwd_ret_h made at T, from a panel known at T."""
    y = forward_label(panel, horizon)
    y = y[y.index <= last_usable_label(T, horizon, embargo)].dropna()
    return float(y.mean()) if len(y) else np.nan
