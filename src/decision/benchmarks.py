"""The four pre-registered benchmark rules.

Each rule receives the returns panel known at month-end T and returns target weights
for next month: {"eq": ..., "bond": ..., "rf": ...} summing to 1 (no leverage, no shorts).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VOL_TARGET = 0.10  # annual


def buy_and_hold(panel: pd.DataFrame) -> dict:
    return {"eq": 1.0, "bond": 0.0, "rf": 0.0}


def sixty_forty(panel: pd.DataFrame) -> dict:
    return {"eq": 0.6, "bond": 0.4, "rf": 0.0}


def vol_target(panel: pd.DataFrame) -> dict:
    """Equity weight = 10% / trailing 12-month realised vol (EUR), capped at 1."""
    r = panel["eq"].dropna().iloc[-12:]
    if len(r) < 12:
        return {"eq": np.nan, "bond": 0.0, "rf": np.nan}
    w = min(1.0, VOL_TARGET / (r.std() * np.sqrt(12)))
    return {"eq": w, "bond": 0.0, "rf": 1 - w}


def sma10(panel: pd.DataFrame) -> dict:
    """Faber: equity if the month-end total-return index is above its 10-month average."""
    idx = panel["eq_index"].dropna().iloc[-10:]
    if len(idx) < 10:
        return {"eq": np.nan, "bond": 0.0, "rf": np.nan}
    w = 1.0 if idx.iloc[-1] > idx.mean() else 0.0
    return {"eq": w, "bond": 0.0, "rf": 1 - w}


RULES = {
    "buy_and_hold": buy_and_hold,
    "60_40": sixty_forty,
    "vol_target_10": vol_target,
    "sma10": sma10,
}
