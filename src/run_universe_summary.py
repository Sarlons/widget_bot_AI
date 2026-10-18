"""Describe the multi-asset universe on the development period (before taxes and costs).

Per market: data start, CAGR, volatility, Sharpe vs EUR cash, max drawdown (all in EUR),
plus average correlations within and across asset classes. Purely descriptive: the
step-B rules were pre-registered before this was run (docs/preregistration.md, section 8).

Run:  .venv\\Scripts\\python -m src.run_universe_summary
Output: results/universe_summary.md
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.features.universe import SERIES, universe_panel
from src.ingest.store import load_all
from src.validation.metrics import max_drawdown
from src.validation.walkforward import DEV_END, assert_no_holdout

RESULTS = Path(__file__).resolve().parents[1] / "results"
WINDOW = ("1976-01-31", "2014-12-31")


def main() -> None:
    records = load_all()
    u = universe_panel(records[records["series"].isin(SERIES)], DEV_END)
    u = u[u.index <= DEV_END]
    # hedged equity series are reserved for the pre-registered test H (amendment B)
    u = u.drop(columns=[c for c in u.columns if c.startswith("eqh_")])
    assert_no_holdout(u.index)
    w = u.loc[WINDOW[0]:WINDOW[1]]
    cash = w["cash"]

    rows = []
    for col in w.columns.drop("cash"):
        r = w[col].dropna()
        ex = r - cash.reindex(r.index)
        years = len(r) / 12
        rows.append({
            "market": col, "first_month": u[col].first_valid_index().strftime("%Y-%m"),
            "from": r.index[0].strftime("%Y-%m"),
            "cagr": (1 + r).prod() ** (1 / years) - 1, "vol": r.std() * np.sqrt(12),
            "sharpe": ex.mean() / ex.std() * np.sqrt(12), "max_dd": max_drawdown(r),
        })
    t = pd.DataFrame(rows)

    c = w.drop(columns="cash").corr(min_periods=60)
    eq = [x for x in c.columns if x.startswith("eq_")]
    bd = [x for x in c.columns if x.startswith("bond_")]

    def avg(a, b):
        m = c.loc[a, b].to_numpy()
        if a == b:
            m = m[~np.eye(len(a), dtype=bool)]
        return np.nanmean(m)

    lines = [
        "# Universe summary (development period, EUR, before costs and taxes)",
        "",
        f"Window {WINDOW[0][:7]} to {WINDOW[1][:7]} (or from the market's first month). "
        "Sharpe vs EUR cash. Holdout 2015+ untouched.",
        f"EUR cash averaged {cash.mean() * 12:.2%} per year.",
        "",
        "| Market | Data from | CAGR | Vol | Sharpe | Max DD |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in t.iterrows():
        lines.append(f"| {r['market']} | {r['first_month']} | {r['cagr']:.1%} | {r['vol']:.1%} | "
                     f"{r['sharpe']:.2f} | {r['max_dd']:.0%} |")
    lines += [
        "",
        "Average pairwise correlation of monthly EUR returns:",
        "",
        f"- equity vs equity: {avg(eq, eq):.2f}",
        f"- bond vs bond: {avg(bd, bd):.2f}",
        f"- equity vs bond: {avg(eq, bd):.2f}",
        "",
        "Bond returns are modelled from monthly-average yields (constant 10y maturity), so",
        "their volatility is slightly understated. Japan bonds start 1989, Italy 1991.",
        "",
    ]
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "universe_summary.md").write_text("\n".join(lines), encoding="utf-8")
    c.round(2).to_csv(RESULTS / "universe_correlations.csv")
    print(f"written {RESULTS / 'universe_summary.md'}")


if __name__ == "__main__":
    main()
