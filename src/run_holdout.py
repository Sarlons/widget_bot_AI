"""The single final test on the locked holdout (2015-01 onwards). Runs ONCE.

Protocol (docs/preregistration.md, section "Holdout freeze"): the final strategy chosen
by the section-12 selection rule and the pre-registered benchmarks are run walk-forward
from 2014-12-31, exactly as in development (same code, costs, taxes), and reported once.
Nothing is tuned afterwards.

Safety: refuses to run unless the freeze section is committed, and refuses to run a
second time (results/holdout_summary.md exists).

Run:  .venv\\Scripts\\python -m src.run_holdout
Outputs: results/holdout_summary.md, results/holdout_monthly.csv, experiments/log.csv
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from src.decision.multi_asset import target_weights, us_buy_hold
from src.experiment_log import log_trial
from src.features.returns import returns_panel
from src.features.universe import universe_panel
from src.features.valuation import cape_percentile
from src.ingest.store import load_all
from src.run_step_b import simulate, stationary_bootstrap
from src.run_step_c import income_at
from src.run_step_d import CAPE_THRESHOLD, NEEDED
from src.validation.metrics import strategy_metrics
from src.validation.walkforward import HOLDOUT_START

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
PREREG = ROOT / "docs" / "preregistration.md"
FREEZE_HEADING = "## 13. Holdout freeze"
HOLDOUT_END = pd.Timestamp("2025-12-31")  # last month with all equity markets (French file)

# frozen in docs/preregistration.md section 13: name -> (rule, target_weights options)
FINAL = ("TSMOM-12 (final)", "tsmom12", {})  # section 13
BENCHMARKS = {
    "B6 equal-risk, no filter": ("eq_risk", {}),
    "B5 global 60/40": ("global_60_40", {}),
    "SMA-10 (step B)": ("sma10", {}),
}


def check_frozen() -> None:
    text = PREREG.read_text(encoding="utf-8")
    if FREEZE_HEADING not in text:
        raise RuntimeError("holdout not frozen: commit the freeze section first")
    dirty = subprocess.run(["git", "status", "--porcelain", str(PREREG)], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        raise RuntimeError("preregistration.md has uncommitted changes")
    if (RESULTS / "holdout_summary.md").exists():
        raise RuntimeError("the holdout has already been run once")


def decide_at(records: pd.DataFrame, T) -> dict:
    u = universe_panel(records, T)
    out = {}
    name, rule, opts = FINAL
    opts = dict(opts)
    if opts.pop("valuation", False):
        opts["equity_scale"] = 0.5 if cape_percentile(records, T) > CAPE_THRESHOLD else 1.0
    out[(name, "eq")] = target_weights(u, rule, "eq", **opts)
    for bname, (brule, bopts) in BENCHMARKS.items():
        out[(bname, "eq")] = target_weights(u, brule, "eq", **bopts)
    out[("US buy-and-hold", "eq")] = us_buy_hold("eq")
    out["income"] = income_at(records, T)
    return out


def main() -> None:
    check_frozen()
    records = load_all()
    records = records[records["series"].isin(NEEDED)]
    decisions = pd.date_range(HOLDOUT_START - pd.offsets.MonthEnd(1),
                              HOLDOUT_END - pd.offsets.MonthEnd(1), freq="ME")
    print(f"holdout walk-forward over {len(decisions)} month-ends ...")
    rows = {T: decide_at(records, T) for T in decisions}

    realised = universe_panel(records, HOLDOUT_END + pd.offsets.MonthEnd(1))
    realised = realised[(realised.index >= HOLDOUT_START) & (realised.index <= HOLDOUT_END)]
    realised["rf"] = realised["cash"]
    usd_tbill = returns_panel(records, HOLDOUT_END)["rf"]

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
    window = (f"{HOLDOUT_START:%Y-%m}", f"{HOLDOUT_END:%Y-%m}")
    no_hedge = pd.DataFrame(index=realised.index)

    names = [FINAL[0]] + list(BENCHMARKS) + ["US buy-and-hold"]
    monthly, metric_rows = {}, []
    for name in names:
        r = simulate(rows, (name, "eq"), window, realised, income, no_hedge)
        m = strategy_metrics(r["ret"], realised["rf"])
        m.update(strategy=name, sharpe_vs_usd_tbill=strategy_metrics(r["ret"], usd_tbill)["sharpe"],
                 turnover_ann=r["turnover"].mean() * 12,
                 drag_ann=(r["gross_ret"] - r["ret"]).mean() * 12)
        metric_rows.append(m)
        monthly[name] = r["ret"]
        log_trial(f"holdout_{name}", {"window": f"{window[0]}..{window[1]}"},
                  {k: m[k] for k in ("mean_log_ret_ann", "sharpe", "max_dd")},
                  notes="final holdout test (run once)")

    # Sharpe difference final - B6, paired stationary bootstrap (descriptive: low power)
    f, b = monthly[FINAL[0]].to_numpy(), monthly["B6 equal-risk, no filter"].to_numpy()
    c = realised["rf"].reindex(monthly[FINAL[0]].index).to_numpy()
    idx = stationary_bootstrap(len(f), 10_000, 12, np.random.default_rng(0))

    def sr(x, cc):
        ex = x - cc
        return ex.mean(axis=-1) / ex.std(axis=-1, ddof=1) * np.sqrt(12)

    d = float(sr(f, c) - sr(b, c))
    d_star = sr(f[idx], c[idx]) - sr(b[idx], c[idx])
    ci = np.percentile(d_star, [2.5, 97.5])

    RESULTS.mkdir(exist_ok=True)
    pd.DataFrame(monthly).to_csv(RESULTS / "holdout_monthly.csv", float_format="%.6f")
    log_excess = float(np.mean(np.log1p(f)) - np.mean(np.log1p(c))) * 12
    write_summary(pd.DataFrame(metric_rows), window, d, ci, log_excess)
    print(f"written {RESULTS / 'holdout_summary.md'}")


def write_summary(metrics: pd.DataFrame, window, d: float, ci, log_excess: float) -> None:
    final = metrics.iloc[0]
    passed = {
        "max drawdown <= 25%": final["max_dd"] <= 0.25,
        f"mean log return above EUR cash ({log_excess:+.2%} per year)": log_excess > 0,
    }
    lines = [
        "# Final holdout test (run once)",
        "",
        f"Window {window[0]} to {window[1]}, never looked at before this run. EUR, after costs",
        "and Italian tax, liquidated at the end. Same code and settings as development.",
        "Frozen protocol: docs/preregistration.md section 13.",
        "",
        "| Strategy | Mean log ret | CAGR | Vol | Sharpe (SE) | Sharpe vs USD T-bill (comparison) | "
        "Max DD | CVaR 5% (m) | Turnover/yr | Cost+tax drag/yr |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for _, m in metrics.iterrows():
        lines.append(
            f"| {m['strategy']} | {m['mean_log_ret_ann']:.2%} | {m['cagr']:.2%} | "
            f"{m['vol_ann']:.1%} | {m['sharpe']:.2f} ({m['sharpe_se']:.2f}) | "
            f"{m['sharpe_vs_usd_tbill']:.2f} | {m['max_dd']:.0%} | {m['cvar5_monthly']:.1%} | "
            f"{m['turnover_ann']:.2f} | {m['drag_ann']:.2%} |")
    lines += ["", "## Pre-registered checks", ""]
    lines += [f"- {k}: **{'pass' if v else 'fail'}**" for k, v in passed.items()]
    lines += [f"- Sharpe of the final strategy minus B6: {d:+.2f} "
              f"(95% bootstrap interval [{ci[0]:+.2f}, {ci[1]:+.2f}]); descriptive only, an "
              "11-year window cannot confirm small differences.", ""]
    (RESULTS / "holdout_summary.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
