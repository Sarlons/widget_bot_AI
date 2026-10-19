"""Checks of the cost and Italian-tax accounting on tiny hand-computable cases."""
import math

import pandas as pd

from src.decision import backtest
from src.decision.backtest import Account


def _frames(eq_returns):
    idx = pd.date_range("2000-01-31", periods=len(eq_returns) + 1, freq="ME")
    weights = pd.DataFrame({"eq": 1.0, "bond": 0.0, "rf": 0.0}, index=idx[:-1])
    realised = pd.DataFrame({"eq": eq_returns, "bond": 0.0, "rf": 0.0}, index=idx[1:])
    income = pd.DataFrame(0.0, index=idx[1:], columns=["eq", "bond", "rf"])
    return weights, realised, income


def test_buy_hold_one_month_gain_taxed_at_liquidation():
    w, r, inc = _frames([0.10])
    out = backtest.run(w, r, inc)
    v = (1 - 0.001) * 1.10                 # buy cost, then +10%
    gain = v - (1 - 0.001)                 # basis = amount invested after cost
    final = v - v * 0.001 - 0.26 * gain    # sell cost + 26% tax (approx: cost not deducted from gain)
    assert math.isclose(1 + out["ret"].iloc[0], final, rel_tol=1e-3)


def test_loss_credit_offsets_later_gain():
    a = Account()
    assert a._capital_gains_tax(-100.0, 2000) == 0.0
    assert math.isclose(a._capital_gains_tax(150.0, 2002), 0.26 * 50)
    assert a._capital_gains_tax(10.0, 2003) == 0.26 * 10  # credit used up


def test_loss_credit_expires_after_four_years():
    a = Account()
    a._capital_gains_tax(-100.0, 2000)
    assert a._capital_gains_tax(100.0, 2005) == 0.26 * 100


def test_govt_bond_gains_taxed_at_12_5_percent():
    a = Account()
    a.value["bond"], a.basis["bond"] = 200.0, 100.0
    paid = a.rebalance({"eq": 0.0, "bond": 0.0, "rf": 1.0}, 2000)
    tax = paid - 200 * 0.0005 - 200 * 0.0005  # minus sell + buy costs
    assert math.isclose(tax, 0.125 * 100, rel_tol=1e-9)


def test_etf_losses_do_not_offset_etf_gains():
    a = Account(assets=("etf_DE", "etf_FR", "rf"))
    a.value["etf_DE"], a.basis["etf_DE"] = 200.0, 100.0   # +100 gain
    a.value["etf_FR"], a.basis["etf_FR"] = 50.0, 150.0    # -100 loss
    paid = a.rebalance({"etf_DE": 0.0, "etf_FR": 0.0, "rf": 1.0}, 2000)
    tax = paid - 250 * 0.0010 - 250 * 0.0005               # sell costs + cash buy cost
    assert math.isclose(tax, 0.26 * 100, rel_tol=1e-9)
    assert a.credits == []
