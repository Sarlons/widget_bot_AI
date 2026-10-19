"""Ranking models of project 2 (pre-registration section 5) and the portfolio rule.

Every model maps the features of month T to one score per eligible index. Training data
at T: feature rows of months t with labels whose 3-month window ended by T-1
(t + 3 <= T - 1), i.e. purged with a 1-month embargo.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor

from src.globalrank.features import FEATURES

SEED = 0


def make_model(name: str):
    if name == "M1":
        return Ridge(alpha=1.0)
    if name == "M2":
        return HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200,
                                             min_samples_leaf=50, random_state=SEED)
    if name == "M3":
        return MLPRegressor(hidden_layer_sizes=(16,), alpha=1e-3, max_iter=500,
                            random_state=SEED)
    raise ValueError(name)


REFIT_EVERY_MONTH = {"M1": True, "M2": False, "M3": False}  # M2/M3 refit each January


def training_set(feats: dict, labels: dict, T) -> tuple[pd.DataFrame, pd.Series]:
    """Stack (features, label) of all months t with t + 3 <= T - 1."""
    last = (pd.Timestamp(T).to_period("M") - 4).to_timestamp(how="end").normalize()
    xs, ys = [], []
    for t, f in feats.items():
        if t <= last and t in labels and not f.empty:
            y = labels[t].reindex(f.index)
            ok = y.notna()
            xs.append(f[ok])
            ys.append(y[ok])
    if not xs:
        return pd.DataFrame(columns=FEATURES), pd.Series(dtype=float)
    return pd.concat(xs), pd.concat(ys)


def scores(name: str, feats: dict, labels: dict, dates: list, cache: dict | None = None
           ) -> dict[pd.Timestamp, pd.Series]:
    """Score of every eligible index at every decision date, walk-forward."""
    out, model = {}, None
    for T in dates:
        f = feats[T]
        if name == "M0":
            out[T] = f["r12_1"]
            continue
        if model is None or REFIT_EVERY_MONTH[name] or T.month == 1:
            X, y = training_set(feats, labels, T)
            model = make_model(name).fit(X.to_numpy(), y.to_numpy())
        out[T] = pd.Series(model.predict(f[FEATURES].to_numpy()), index=f.index)
    return out


def holdings(score_seq: dict[pd.Timestamp, pd.Series]) -> dict[pd.Timestamp, list[str]]:
    """Top third by score; a held index is kept until it falls out of the top half."""
    out, held = {}, []
    for T, s in score_seq.items():
        n = len(s)
        order = s.sort_values(ascending=False).index.tolist()
        top_third = order[:math.ceil(n / 3)]
        top_half = set(order[:math.ceil(n / 2)])
        held = [h for h in held if h in top_half] + [c for c in top_third if c not in held]
        out[T] = sorted(held)
    return out


def drifted_weights(hold: dict, panel: pd.DataFrame) -> dict[pd.Timestamp, dict]:
    """Equal weight when the holdings change; otherwise let the weights drift (no trades)."""
    out, prev_w, prev_h = {}, None, None
    for T, h in hold.items():
        if prev_h is not None and h == prev_h:
            r = panel.loc[T, h]  # return of month T, known at T
            w = {a: prev_w[a] * (1 + r[a]) for a in h}
            tot = sum(w.values())
            w = {a: v / tot for a, v in w.items()}
        else:
            w = {a: 1 / len(h) for a in h}
        out[T], prev_w, prev_h = w, w, h
    return out


def equal_weight(feats: dict, dates: list) -> dict[pd.Timestamp, dict]:
    return {T: {a: 1 / len(feats[T]) for a in feats[T].index} for T in dates}


def turnover_proxy(weights: dict) -> float:
    vals = list(weights.values())
    keys = set().union(*vals)
    t = [sum(abs(b.get(k, 0) - a.get(k, 0)) for k in keys) / 2 for a, b in zip(vals, vals[1:])]
    return float(np.mean(t)) * 12 if t else 0.0
