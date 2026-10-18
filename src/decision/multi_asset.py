"""Step-B multi-asset rules (pre-registration sections 8 and 10), decided at month-end T.

    w = target_weights(u, rule, sleeve="eq")      # u = universe_panel(records, T)

`u` must contain only data known at T (rows up to T). Returns a dict asset -> weight,
including the EUR cash asset "rf"; weights are >= 0 and sum to 1.

Rules:
  tsmom12  hold a market if its 12-month return in excess of EUR cash > 0
  sma10    hold a market if its total-return index > its 10-month average
  eq_risk  benchmark 6: every eligible market (no trend filter)
then risk weighting with the class budget and 10% vol target (section 10).
  global_60_40  benchmark 5: 60% equal weight equities, 40% equal weight bonds.

sleeve = "eq" (unhedged equities) or "eqh" (currency-hedged equities, test H).
classes = ("eq", "bond") for step B, ("eq", "bond", "alt") for test C: "alt" = currency
deposits + gold; every non-empty or empty class gets 1/len(classes) of the risk budget.
Gold is known with a 1-month lag (monthly-average prices), so all its statistics use
months t-12..t-1 (pre-registration section 11).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.features.universe import BONDS, CURRENCIES, EQUITY

TARGET_VOL = 0.10
VOL_MONTHS = 12
CORR_MONTHS = 36
RULES = ("tsmom12", "sma10", "eq_risk", "global_60_40")
ALT = [f"fx_{c}" for c in CURRENCIES] + ["gold"]


def eligible(u: pd.DataFrame, cols: list[str], months: int = VOL_MONTHS) -> list[str]:
    """Markets whose last `months` monthly returns (up to T) are all present."""
    tail = u[cols].iloc[-months:]
    return [c for c in cols if len(tail) == months and tail[c].notna().all()]


def signal(u: pd.DataFrame, col: str, rule: str) -> bool:
    r = u[col].iloc[-VOL_MONTHS:]
    if rule == "tsmom12":
        cash = u["cash"].iloc[-VOL_MONTHS:]
        return bool((1 + r).prod() - (1 + cash).prod() > 0)
    if rule == "sma10":
        idx = (1 + r).cumprod()  # index over the last 12 months; the ratio is scale-free
        return bool(idx.iloc[-1] > idx.iloc[-10:].mean())
    if rule == "eq_risk":
        return True
    raise ValueError(rule)


def covariance(u: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Annual covariance: 12-month vols, 36-month correlations if all have them, else diagonal."""
    vol = u[cols].iloc[-VOL_MONTHS:].std() * np.sqrt(12)
    corr = pd.DataFrame(np.eye(len(cols)), index=cols, columns=cols)
    if len(eligible(u, cols, CORR_MONTHS)) == len(cols):
        corr = u[cols].iloc[-CORR_MONTHS:].corr()
    return corr * np.outer(vol, vol)


def risk_weights(u: pd.DataFrame, selected: dict[str, list[str]]) -> dict[str, float]:
    """Inverse-vol inside each class, equal risk per class, 10% vol, cap 100%."""
    chosen = [c for cols in selected.values() for c in cols]
    if not chosen:
        return {}
    cov = covariance(u, chosen)
    vol = np.sqrt(np.diag(cov))
    v = pd.Series(0.0, index=chosen)
    for cols in selected.values():
        if not cols:
            continue
        p = pd.Series(1 / vol[[chosen.index(c) for c in cols]], index=cols)
        p /= p.sum()
        sigma_k = float(np.sqrt(p @ cov.loc[cols, cols] @ p))
        v[cols] += p / sigma_k / len(selected)
    w = v * TARGET_VOL / float(np.sqrt(v @ cov @ v))
    if w.sum() > 1:
        w /= w.sum()
    return w.to_dict()


def target_weights(u: pd.DataFrame, rule: str, sleeve: str = "eq",
                   classes: tuple = ("eq", "bond")) -> dict[str, float]:
    eq_cols = eligible(u, [f"{sleeve}_{c}" for c in EQUITY])
    bd_cols = eligible(u, [f"bond_{c}" for c in BONDS])
    if "alt" in classes:
        u = u.assign(gold=u["gold"].shift(1))  # row T holds gold's return of T-1
        alt_cols = eligible(u, ALT)
    if rule == "global_60_40":
        w = {c: 0.6 / len(eq_cols) for c in eq_cols} if eq_cols else {}
        w.update({c: 0.4 / len(bd_cols) for c in bd_cols} if bd_cols else {})
    else:
        selected = {"eq": [c for c in eq_cols if signal(u, c, rule)],
                    "bond": [c for c in bd_cols if signal(u, c, rule)]}
        if "alt" in classes:
            selected["alt"] = [c for c in alt_cols if signal(u, c, rule)]
        w = risk_weights(u, selected)
    w = {k: float(v) for k, v in w.items() if v > 0}
    w["rf"] = max(0.0, 1.0 - sum(w.values()))
    return w


def us_buy_hold(sleeve: str = "eq") -> dict[str, float]:
    """US equity buy-and-hold (test H pair): 100% in the US equity sleeve."""
    return {f"{sleeve}_US": 1.0, "rf": 0.0}
