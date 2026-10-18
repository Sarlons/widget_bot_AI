"""Portfolio accounting in EUR with transaction costs and Italian taxes.

Each month-end T: the rule chooses target weights using only data known at T; we trade
to them (paying costs and capital-gains tax), then hold for one month.

Italian tax model (approximation of the 'regime amministrato', direct holdings):
  * Income (dividends, coupons, T-bill interest) is taxed when earned:
      dividends 26%, government-bond / T-bill interest 12.5%.
    (US withholding on dividends ignored; it would add ~4-11 pp of drag on dividends.)
  * Capital gains are taxed when REALISED (on sale), at 26%. Government bonds count at
    48.08% of the gain (= 12.5% effective); the same factor applies to their losses.
  * Net realised losses become credits usable against future capital gains (not income)
    until the end of the 4th following calendar year.
  * Cost basis = average cost. FX gains are part of the EUR capital gain.
  * At the end of the period everything is sold and the liquidation tax is charged in
    the last month, so buy-and-hold is not flattered by never-taxed gains.
Costs: 10 bp of traded value for equity, 5 bp for bonds and T-bills (one-way).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

ASSETS = ("eq", "bond", "rf")
COST = {"eq": 0.0010, "bond": 0.0005, "rf": 0.0005}
CG_TAX = 0.26
GOVT_FACTOR = 12.5 / 26  # 0.4808: share of a govt-bond gain/loss that enters the base
CG_FACTOR = {"eq": 1.0, "bond": GOVT_FACTOR, "rf": GOVT_FACTOR}
INCOME_TAX = {"eq": 0.26, "bond": 0.125, "rf": 0.125}
CREDIT_YEARS = 4


@dataclass
class Account:
    value: dict = field(default_factory=lambda: {a: 0.0 for a in ASSETS})
    basis: dict = field(default_factory=lambda: {a: 0.0 for a in ASSETS})
    credits: list = field(default_factory=list)  # [amount, expiry_year]
    cost: dict = field(default_factory=lambda: dict(COST))  # one-way cost per asset

    def wealth(self) -> float:
        return sum(self.value.values())

    def _capital_gains_tax(self, base: float, year: int) -> float:
        """Apply loss credits (oldest first) to a realised taxable base; return tax due."""
        self.credits = [c for c in self.credits if c[1] >= year and c[0] > 0]
        if base < 0:
            self.credits.append([-base, year + CREDIT_YEARS])
            return 0.0
        for c in self.credits:
            used = min(c[0], base)
            c[0] -= used
            base -= used
        return CG_TAX * base

    def rebalance(self, target: dict, year: int) -> float:
        """Trade to target weights; returns costs + tax paid (EUR)."""
        W = self.wealth()
        base, cost = 0.0, 0.0
        for a in ASSETS:
            trade = target[a] * W - self.value[a]
            cost += abs(trade) * self.cost[a]
            if trade < 0 and self.value[a] > 0:  # sale: realise part of the gain
                frac = -trade / self.value[a]
                base += frac * (self.value[a] - self.basis[a]) * CG_FACTOR[a]
                self.basis[a] *= 1 - frac
            elif trade > 0:
                self.basis[a] += trade
            self.value[a] += trade
        paid = cost + self._capital_gains_tax(base, year)
        self._deduct(paid)
        return paid

    def _deduct(self, amount: float) -> None:
        """Pay an amount pro-rata from all positions (value and basis scaled alike)."""
        W = self.wealth()
        if amount <= 0 or W <= 0:
            return
        k = 1 - amount / W
        for a in ASSETS:
            self.value[a] *= k
            self.basis[a] *= k

    def grow(self, ret: dict, income_yield: dict) -> None:
        """One month of returns (EUR); income part is taxed now and reinvested."""
        for a in ASSETS:
            v0 = self.value[a]
            income = v0 * income_yield[a]
            tax = income * INCOME_TAX[a]
            self.value[a] = v0 * (1 + ret[a]) - tax
            self.basis[a] += income - tax  # reinvested net income has its own cost

    def liquidation_tax(self, year: int) -> float:
        """Sell everything at the end: pay costs and tax on all unrealised gains."""
        base = sum((self.value[a] - self.basis[a]) * CG_FACTOR[a] for a in ASSETS)
        cost = sum(self.value[a] * self.cost[a] for a in ASSETS)
        paid = cost + self._capital_gains_tax(base, year)
        self._deduct(paid)
        return paid


def run(weights: pd.DataFrame, realised: pd.DataFrame, income: pd.DataFrame,
        liquidate_at_end: bool = True, cost: dict | None = None) -> pd.DataFrame:
    """Simulate the account.

    weights  : index = decision dates T (month-ends), columns eq/bond/rf
    realised : EUR returns for each month, index = month-end of the return month
    income   : income yields (monthly) for each month, same index as realised
    cost     : optional one-way cost per asset (default COST); e.g. 0 for a EUR deposit
    Returns a DataFrame indexed by return month with the net portfolio return,
    gross (pre-cost, pre-tax) return, turnover and costs+taxes paid.
    """
    acct = Account(cost=dict(cost or COST))
    acct.value["rf"] = acct.basis["rf"] = 1.0  # start with 1 EUR in cash
    next_month = {T: (T.to_period("M") + 1).to_timestamp(how="end").normalize()
                  for T in weights.index}
    dates = [T for T in weights.index if next_month[T] in realised.index]
    rows = []
    for i, T in enumerate(dates):
        nxt = next_month[T]
        w = weights.loc[T].to_dict()
        W0 = acct.wealth()
        before = {a: acct.value[a] / W0 for a in ASSETS}
        turnover = sum(abs(w[a] - before[a]) for a in ASSETS) / 2
        paid = _initial(acct, w) if i == 0 else acct.rebalance(w, T.year)
        r = realised.loc[nxt]
        acct.grow({a: r[a] for a in ASSETS}, {a: income.loc[nxt, a] for a in ASSETS})
        if liquidate_at_end and i == len(dates) - 1:
            paid += acct.liquidation_tax(nxt.year)
        rows.append({"date": nxt, "ret": acct.wealth() / W0 - 1,
                     "gross_ret": sum(w[a] * r[a] for a in ASSETS),
                     "turnover": 0.0 if i == 0 else turnover, "paid": paid / W0})
    return pd.DataFrame(rows).set_index("date")


def _initial(acct: Account, w: dict) -> float:
    """Initial allocation from cash: buy at cost, no tax (cash basis = value)."""
    W = acct.wealth()
    cost = sum(w[a] * W * acct.cost[a] for a in ASSETS if a != "rf")
    for a in ASSETS:
        acct.value[a] = acct.basis[a] = w[a] * W
    acct._deduct(cost)
    return cost
