"""Step C / test C: does a third class (currency deposits + gold) improve the step-B rules?

Pre-registered in docs/preregistration.md section 11. For every month-end T of
1975-12..2014-11, decide TSMOM-12, SMA-10 and the no-filter equal-risk benchmark with
two classes (equity, bond: = step B) and three classes (equity, bond, alt), simulate both
in EUR after costs and Italian tax, and compare the Sharpe ratios with the paired
stationary bootstrap used for test H.

The two-class runs are identical to the step-B trials already logged, so only the
three-class runs are logged as new trials.

Run:  .venv\\Scripts\\python -m src.run_step_c
Outputs: results/step_c_summary.md, results/step_c_monthly.csv, experiments/log.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.decision.multi_asset import ALT, target_weights
from src.experiment_log import log_trial
from src.features.returns import returns_panel
from src.features.universe import BONDS, CURRENCIES, SERIES, local_short_rate, universe_panel
from src.ingest.store import as_of, load_all
from src.run_step_b import NEEDED as B_NEEDED
from src.run_step_b import bond_yield_col, simulate, test_h
from src.validation.metrics import max_drawdown, strategy_metrics
from src.validation.walkforward import DEV_END, assert_no_holdout, month_ends

RESULTS = Path(__file__).resolve().parents[1] / "results"
NEEDED = sorted(set(B_NEEDED + SERIES))
WINDOW = ("1976-01", "2014-12")
C_RULES = ("tsmom12", "sma10", "eq_risk")
VARIANTS = {"2 classes": ("eq", "bond"), "3 classes": ("eq", "bond", "alt")}


def decide_at(records: pd.DataFrame, T) -> dict:
    """Weights of every rule and variant plus income yields, using only data known at T."""
    u = universe_panel(records, T)
    out = {(rule, var): target_weights(u, rule, "eq", classes)
           for rule in C_RULES for var, classes in VARIANTS.items()}
    out["income"] = income_at(records, T)
    return out


def income_at(records: pd.DataFrame, T) -> dict:
    """Income yields of month T+1 for the tax accounting, known at T."""
    d = as_of(records, T, SERIES)
    dp = as_of(records, T, ["shiller_D", "shiller_P"]).ffill().iloc[-1]
    y = as_of(records, T, [bond_yield_col(c) for c in BONDS]).ffill().iloc[-1]
    income = {"eq": dp["shiller_D"] / dp["shiller_P"] / 12}
    income |= {f"bond_{c}": y[bond_yield_col(c)] / 12 for c in BONDS
               if pd.notna(y[bond_yield_col(c)])}
    for cur, (c, _, _) in CURRENCIES.items():
        rate = local_short_rate(d, c).reindex(d.index)
        if T in rate.index and pd.notna(rate.loc[T]):
            income[f"fx_{cur}"] = rate.loc[T] / 12  # deposit interest of month T+1
    return income


def main() -> None:
    records = load_all()
    records = records[records["series"].isin(NEEDED)]
    decisions = month_ends(pd.Timestamp(WINDOW[0]) - pd.offsets.MonthEnd(1),
                           DEV_END - pd.offsets.MonthEnd(1))
    assert_no_holdout(decisions)
    print(f"walk-forward over {len(decisions)} month-ends ...")
    rows = {T: decide_at(records, T) for T in decisions}

    # realised returns of 1976-2014: gold of 2014-12 is published in 2015-01 (lag 1), so read
    # one month later; only observations up to 2014-12 are kept (nothing of the holdout)
    realised = universe_panel(records, DEV_END + pd.offsets.MonthEnd(1))
    realised = realised[realised.index <= DEV_END]
    assert_no_holdout(realised.index)
    realised["rf"] = realised["cash"]
    usd_tbill = returns_panel(records, DEV_END)["rf"]

    inc = pd.DataFrame({T: rows[T]["income"] for T in decisions}).T
    inc.index = [(T.to_period("M") + 1).to_timestamp(how="end").normalize() for T in inc.index]
    income = pd.DataFrame(index=inc.index)
    for col in realised.columns:
        if col.startswith(("eq_", "eqh_")):
            income[col] = inc["eq"]
        elif col.startswith(("bond_", "fx_")) and col in inc:
            income[col] = inc[col]
    income["gold"] = 0.0
    income["rf"] = realised["rf"].reindex(income.index)
    no_hedge = pd.DataFrame(index=realised.index)

    metric_rows, tests, monthly = [], [], {}
    for rule in C_RULES:
        res = {}
        for var in VARIANTS:
            key = (rule, var)
            res[var] = r = simulate(rows, key, WINDOW, realised, income, no_hedge)
            m = strategy_metrics(r["ret"], realised["rf"])
            m.update(rule=rule, variant=var,
                     sharpe_vs_usd_tbill=strategy_metrics(r["ret"], usd_tbill)["sharpe"],
                     turnover_ann=r["turnover"].mean() * 12,
                     drag_ann=(r["gross_ret"] - r["ret"]).mean() * 12)
            w = pd.DataFrame({T: rows[T][key] for T in rows}).T.fillna(0.0)
            m["alt_weight_avg"] = float(w[[c for c in ALT if c in w]].sum(axis=1).mean())
            metric_rows.append(m)
            monthly[f"{rule} | {var}"] = r["ret"]
            if var == "3 classes":
                log_trial(f"stepc_{rule}_3classes", {"window": f"{WINDOW[0]}..{WINDOW[1]}",
                                                     "cash": "EUR cash"},
                          {k: m[k] for k in ("mean_log_ret_ann", "sharpe", "max_dd")},
                          notes="pre-registered test C, EUR after costs and tax")
        t = test_h(res["3 classes"]["ret"], res["2 classes"]["ret"], realised["rf"])
        t.update(rule=rule, new_max_dd=max_drawdown(res["3 classes"]["ret"]))
        tests.append(t)

    RESULTS.mkdir(exist_ok=True)
    pd.DataFrame(monthly).to_csv(RESULTS / "step_c_monthly.csv", float_format="%.6f")
    write_summary(pd.DataFrame(metric_rows), tests)
    print(f"written {RESULTS / 'step_c_summary.md'}")


def write_summary(metrics: pd.DataFrame, tests: list[dict]) -> None:
    names = {"tsmom12": "TSMOM-12", "sma10": "SMA-10", "eq_risk": "Equal-risk, no filter (B6)"}
    lines = [
        "# Step C: currencies and gold as a third class (development period)",
        "",
        f"Window {WINDOW[0]} to {WINDOW[1]}. EUR, after costs and Italian tax, liquidated at",
        "the end. Sharpe vs EUR cash; `vs USD T-bill (comparison)` for reference only.",
        "Alt = 3-month deposits in USD, GBP, JPY, CHF, CAD, AUD and a gold ETC.",
        "Holdout 2015+ untouched. Rules: docs/preregistration.md sections 10-11.",
        "",
        "| Rule | Classes | Mean log ret | CAGR | Vol | Sharpe (SE) | Sharpe vs USD T-bill "
        "(comparison) | Max DD | CVaR 5% (m) | Avg alt weight | Turnover/yr | Cost+tax drag/yr |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for _, m in metrics.iterrows():
        lines.append(
            f"| {names[m['rule']]} | {m['variant']} | {m['mean_log_ret_ann']:.2%} | "
            f"{m['cagr']:.2%} | {m['vol_ann']:.1%} | {m['sharpe']:.2f} ({m['sharpe_se']:.2f}) | "
            f"{m['sharpe_vs_usd_tbill']:.2f} | {m['max_dd']:.0%} | {m['cvar5_monthly']:.1%} | "
            f"{m['alt_weight_avg']:.0%} | {m['turnover_ann']:.2f} | {m['drag_ann']:.2%} |")
    lines += ["", "## Test C: 3 classes minus 2 classes", "",
              "Paired stationary bootstrap (mean block 12, 10,000 draws). The 3-class version",
              "is adopted only if its Sharpe is higher with p < 0.05 and max DD <= 25%.", "",
              "| Rule | Sharpe diff | 95% CI | p | Max DD diff | 95% CI | Adopted? |",
              "|---|---|---|---|---|---|---|"]
    for t in tests:
        adopt = t["sharpe_diff"] > 0 and t["p_value"] < 0.05 and t["new_max_dd"] <= 0.25
        lines.append(
            f"| {names[t['rule']]} | {t['sharpe_diff']:+.2f} | "
            f"[{t['sharpe_diff_ci'][0]:+.2f}, {t['sharpe_diff_ci'][1]:+.2f}] | {t['p_value']:.3f} | "
            f"{t['max_dd_diff']:+.0%} | [{t['max_dd_diff_ci'][0]:+.0%}, "
            f"{t['max_dd_diff_ci'][1]:+.0%}] | {'yes' if adopt else 'no'} |")
    lines += ["",
              "Limits: gold uses monthly-average prices (signals skip the last month); EUR per",
              "USD before 1999 is an OECD monthly average for every EUR conversion; Italian tax on",
              "currency gains simplified to 26% on realised gains.", ""]
    (RESULTS / "step_c_summary.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
