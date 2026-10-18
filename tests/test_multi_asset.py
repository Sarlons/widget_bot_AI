"""Checks of the step-B weighting rules on small synthetic panels."""
import math

import numpy as np
import pandas as pd

from src.decision import backtest
from src.decision.multi_asset import risk_weights, signal, target_weights
from src.features.universe import BONDS, EQUITY


def _panel(n=40, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2000-01-31", periods=n, freq="ME")
    cols = {f"eq_{c}": rng.normal(0.008, 0.05, n) for c in EQUITY}
    cols |= {f"bond_{c}": rng.normal(0.004, 0.02, n) for c in BONDS}
    cols["cash"] = np.full(n, 0.002)
    return pd.DataFrame(cols, index=idx)


def test_weights_long_only_capped_and_sum_to_one():
    u = _panel()
    for rule in ("tsmom12", "sma10", "eq_risk", "global_60_40"):
        w = target_weights(u, rule)
        assert all(v >= 0 for v in w.values())
        assert math.isclose(sum(w.values()), 1.0)


def test_eq_risk_hits_vol_target_when_uncapped():
    u = _panel()
    u.loc[:, [c for c in u.columns if c != "cash"]] *= 10  # high vol: target binds, no cap
    sel = {"eq": [f"eq_{c}" for c in EQUITY], "bond": [f"bond_{c}" for c in BONDS]}
    w = pd.Series(risk_weights(u, sel))
    cov = u[w.index].iloc[-36:].corr() * np.outer(u[w.index].iloc[-12:].std(),
                                                    u[w.index].iloc[-12:].std()) * 12
    assert w.sum() < 1
    assert math.isclose(float(np.sqrt(w @ cov @ w)), 0.10, rel_tol=1e-9)


def test_market_with_missing_history_is_not_eligible():
    u = _panel()
    u.loc[u.index[-5], "eq_JP"] = np.nan
    assert "eq_JP" not in target_weights(u, "eq_risk")


def test_tsmom_signal_compares_with_cash():
    u = _panel()
    u["eq_US"] = 0.001  # positive but below cash (0.002)
    assert not signal(u, "eq_US", "tsmom12")


def test_hedge_pnl_loss_becomes_credit():
    a = backtest.Account(assets=("eqh_US", "rf"))
    a.value["eqh_US"] = a.basis["eqh_US"] = 100.0
    a.grow({"eqh_US": -0.05, "rf": 0.0}, {"eqh_US": 0.0, "rf": 0.0}, {"eqh_US": -0.05}, 2000)
    assert math.isclose(a.value["eqh_US"], 95.0)
    assert math.isclose(a.basis["eqh_US"], 95.0)  # the hedge loss is realised
    assert a.credits[0][0] == 5.0


def test_three_classes_share_risk_budget():
    from src.decision.multi_asset import ALT
    u = _panel()
    rng = np.random.default_rng(3)
    for c in ALT:
        u[c] = rng.normal(0.003, 0.03, len(u))
    w = target_weights(u, "eq_risk", classes=("eq", "bond", "alt"))
    assert any(k in w for k in ALT)
    assert math.isclose(sum(w.values()), 1.0)
