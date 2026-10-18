"""Step D: crash-response variants D1-D3 and valuation overlay E on TSMOM-12.

Pre-registered in docs/preregistration.md section 12. Base = TSMOM-12 with the classes
chosen by test C (BASE_CLASSES), unhedged equities. Each variant is simulated in EUR after
costs and Italian tax on 1976-01..2014-12, logged as one trial, and compared with the base
(paired stationary bootstrap of the Sharpe difference, as tests H and C).

Run:  .venv\\Scripts\\python -m src.run_step_d
Outputs: results/step_d_summary.md, results/step_d_monthly.csv, experiments/log.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.decision.multi_asset import target_weights
from src.experiment_log import log_trial
from src.features.returns import returns_panel
from src.features.universe import universe_panel
from src.features.valuation import SERIES as CAPE_SERIES
from src.features.valuation import cape_percentile
from src.ingest.store import load_all
from src.run_step_b import simulate, test_h
from src.run_step_c import NEEDED as C_NEEDED
from src.run_step_c import income_at
from src.validation.metrics import max_drawdown, strategy_metrics
from src.validation.walkforward import DEV_END, assert_no_holdout, month_ends

RESULTS = Path(__file__).resolve().parents[1] / "results"
NEEDED = sorted(set(C_NEEDED + CAPE_SERIES))
WINDOW = ("1976-01", "2014-12")
BASE_CLASSES = ("eq", "bond")  # test C did not adopt the third class (results/step_c_summary.md)
CAPE_THRESHOLD = 0.90
VARIANTS = {  # name -> target_weights options
    "base": {},
    "D1": {"speeds": True},
    "D2": {"fast_vol": True},
    "D3": {"speeds": True, "fast_vol": True},
}


def decide_at(records: pd.DataFrame, T) -> dict:
    """Weights of the base, D1-D3 and E plus income yields, using only data known at T."""
    u = universe_panel(records, T)
    out = {(name, "eq"): target_weights(u, "tsmom12", "eq", BASE_CLASSES, **opts)
           for name, opts in VARIANTS.items()}
    pct = cape_percentile(records, T)
    out["cape_pct"] = pct
    out[("E", "eq")] = target_weights(u, "tsmom12", "eq", BASE_CLASSES,
                                      equity_scale=0.5 if pct > CAPE_THRESHOLD else 1.0)
    out["income"] = income_at(records, T)
    return out


def main() -> None:
    records = load_all()
    records = records[records["series"].isin(NEEDED)]
    decisions = month_ends(pd.Timestamp(WINDOW[0]) - pd.offsets.MonthEnd(1),
                           DEV_END - pd.offsets.MonthEnd(1))
    assert_no_holdout(decisions)
    print(f"walk-forward over {len(decisions)} month-ends ...")
    rows = {T: decide_at(records, T) for T in decisions}

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

    res, metric_rows, monthly = {}, [], {}
    for name in list(VARIANTS) + ["E"]:
        res[name] = r = simulate(rows, (name, "eq"), WINDOW, realised, income, no_hedge)
        m = strategy_metrics(r["ret"], realised["rf"])
        m.update(variant=name, sharpe_vs_usd_tbill=strategy_metrics(r["ret"], usd_tbill)["sharpe"],
                 turnover_ann=r["turnover"].mean() * 12,
                 drag_ann=(r["gross_ret"] - r["ret"]).mean() * 12,
                 oct_1987=float(r["ret"].get(pd.Timestamp("1987-10-31"), float("nan"))))
        metric_rows.append(m)
        monthly[name] = r["ret"]
        if name != "base":  # the base is the step-B TSMOM-12 trial, already logged
            log_trial(f"stepd_tsmom12_{name}", {"window": f"{WINDOW[0]}..{WINDOW[1]}",
                                                "classes": list(BASE_CLASSES)},
                      {k: m[k] for k in ("mean_log_ret_ann", "sharpe", "max_dd")},
                      notes="pre-registered step D, EUR after costs and tax")
    tests = []
    for name in list(VARIANTS)[1:] + ["E"]:
        t = test_h(res[name]["ret"], res["base"]["ret"], realised["rf"])
        t.update(variant=name, new_max_dd=max_drawdown(res[name]["ret"]))
        tests.append(t)
    share_e = sum(rows[T]["cape_pct"] > CAPE_THRESHOLD for T in decisions) / len(decisions)

    RESULTS.mkdir(exist_ok=True)
    pd.DataFrame(monthly).to_csv(RESULTS / "step_d_monthly.csv", float_format="%.6f")
    write_summary(pd.DataFrame(metric_rows), tests, share_e)
    print(f"written {RESULTS / 'step_d_summary.md'}")


def write_summary(metrics: pd.DataFrame, tests: list[dict], share_e: float) -> None:
    names = {"base": "TSMOM-12 (base)", "D1": "D1 multi-speed trend", "D2": "D2 fast volatility",
             "D3": "D3 = D1 + D2", "E": "E valuation overlay"}
    lines = [
        "# Step D: crash response and valuation overlay (development period)",
        "",
        f"Window {WINDOW[0]} to {WINDOW[1]}, classes {', '.join(BASE_CLASSES)}. EUR, after costs",
        "and Italian tax, liquidated at the end. Sharpe vs EUR cash. Holdout 2015+ untouched.",
        f"E halved the equity budget in {share_e:.0%} of the months (US CAPE above the 90th",
        "percentile of its point-in-time history).",
        "",
        "| Variant | Mean log ret | CAGR | Vol | Sharpe (SE) | Sharpe vs USD T-bill (comparison) | "
        "Max DD | CVaR 5% (m) | Oct 1987 | Turnover/yr | Cost+tax drag/yr |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for _, m in metrics.iterrows():
        lines.append(
            f"| {names[m['variant']]} | {m['mean_log_ret_ann']:.2%} | {m['cagr']:.2%} | "
            f"{m['vol_ann']:.1%} | {m['sharpe']:.2f} ({m['sharpe_se']:.2f}) | "
            f"{m['sharpe_vs_usd_tbill']:.2f} | {m['max_dd']:.0%} | {m['cvar5_monthly']:.1%} | "
            f"{m['oct_1987']:.1%} | {m['turnover_ann']:.2f} | {m['drag_ann']:.2%} |")
    lines += ["", "## Variant minus base", "",
              "Paired stationary bootstrap (mean block 12, 10,000 draws).", "",
              "| Variant | Sharpe diff | 95% CI | p | Max DD diff | 95% CI |",
              "|---|---|---|---|---|---|"]
    for t in tests:
        lines.append(
            f"| {names[t['variant']]} | {t['sharpe_diff']:+.2f} | "
            f"[{t['sharpe_diff_ci'][0]:+.2f}, {t['sharpe_diff_ci'][1]:+.2f}] | {t['p_value']:.3f} | "
            f"{t['max_dd_diff']:+.0%} | [{t['max_dd_diff_ci'][0]:+.0%}, "
            f"{t['max_dd_diff_ci'][1]:+.0%}] |")
    lines += ["", "All variants stay candidates for the final selection rule (section 12).", ""]
    (RESULTS / "step_d_summary.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
