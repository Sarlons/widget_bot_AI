"""Step 4 baseline: historical-mean forecast + the four benchmark rules, walk-forward.

For every month-end T in the development period (never the 2015+ holdout):
  1. read the data known at T (returns_panel -> as_of),
  2. forecast next 1m and 12m log excess returns with the expanding historical mean
     (purged + 1-month embargo),
  3. compute each benchmark rule's target weights,
then score forecasts out of sample and simulate the rules in EUR after costs and tax.

Run:  .venv\\Scripts\\python -m src.run_baseline
Outputs: results/baseline_summary.md, results/baseline_monthly.csv, experiments/log.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.decision import backtest
from src.decision.benchmarks import RULES
from src.experiment_log import log_trial
from src.features.returns import SERIES as RET_SERIES
from src.features.returns import returns_panel
from src.ingest.store import as_of, load_all
from src.models import historical_mean
from src.validation.metrics import clark_west, oos_r2, strategy_metrics
from src.validation.walkforward import DEV_END, assert_no_holdout, month_ends

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
HORIZONS = (1, 12)
FIRST_DECISION = pd.Timestamp("1927-06-30")  # 12 months of CRSP data for the vol rule
FIRST_FORECAST = pd.Timestamp("1946-12-31")  # >= 20 years of training labels
NEEDED = RET_SERIES + ["shiller_D", "shiller_P"]


def decide_at(records: pd.DataFrame, T) -> dict:
    """Everything decided at month-end T, using only data available at T."""
    panel = returns_panel(records, T)
    out = {f"f{h}": historical_mean.forecast(panel, T, h) for h in HORIZONS}
    for name, rule in RULES.items():
        out[name] = rule(panel)
    # income yields for next month's tax accounting (known at T)
    dp = as_of(records, T, ["shiller_D", "shiller_P"]).ffill().iloc[-1]
    rate = as_of(records, T, ["fred_GS10", "shiller_rate"]).ffill().iloc[-1]
    long_rate = rate["fred_GS10"] if pd.notna(rate["fred_GS10"]) else rate["shiller_rate"]
    out["income"] = {"eq": dp["shiller_D"] / dp["shiller_P"] / 12, "bond": long_rate / 12}
    return out


def main() -> None:
    records = load_all()
    records = records[records["series"].isin(NEEDED)]
    decisions = month_ends(FIRST_DECISION, DEV_END - pd.offsets.MonthEnd(1))
    assert_no_holdout(decisions)

    print(f"walk-forward over {len(decisions)} month-ends ...")
    rows = {T: decide_at(records, T) for T in decisions}

    # realised returns of the development period (all known at DEV_END)
    realised = returns_panel(records, DEV_END)
    realised = realised[realised.index <= DEV_END]
    assert_no_holdout(realised.index)

    # ---- forecasts ----
    fc_lines = []
    for h in HORIZONS:
        y = historical_mean.forward_label(realised, h)
        f = pd.Series({T: rows[T][f"f{h}"] for T in decisions})
        df = pd.DataFrame({"y": y, "f": f}).loc[FIRST_FORECAST:].dropna()
        zero = pd.Series(0.0, index=df.index)
        r2 = oos_r2(df["y"], df["f"], zero)
        cw = clark_west(df["y"], df["f"], zero, h)
        log_trial(f"hist_mean_h{h}", {"horizon": h, "embargo": 1},
                  {"oos_r2_vs_zero": r2, **cw, "n": len(df)}, notes="baseline forecast")
        fc_lines.append(f"| {h}m | {df.index[0]:%Y-%m} to {df.index[-1]:%Y-%m} | {len(df)} | "
                        f"{df['f'].iloc[-1] * 12 / h:.2%} | {r2:.4f} | {cw['cw_stat']:.2f} | "
                        f"{cw['cw_pvalue']:.3f} |")

    # ---- benchmark strategies ----
    income = pd.DataFrame({T: rows[T]["income"] for T in decisions}).T
    income.index = [(T.to_period("M") + 1).to_timestamp(how="end").normalize() for T in income.index]
    income["rf"] = realised["rf_usd"].reindex(income.index)
    monthly, metric_rows = {}, []
    periods = [("1927-07", "2014-12"), ("1947-01", "2014-12"), ("1971-01", "2014-12")]
    for name in RULES:
        w = pd.DataFrame({T: rows[T][name] for T in decisions}).T.dropna()
        for start, end in periods:
            # each period is simulated from scratch (fresh account, liquidated at the end)
            ws = w.loc[(pd.Timestamp(start) - pd.offsets.MonthEnd(1)):end]
            res = backtest.run(ws, realised, income)
            m = strategy_metrics(res["ret"], realised["rf"])
            m.update(rule=name, turnover_ann=res["turnover"].mean() * 12,
                     drag_ann=(res["gross_ret"] - res["ret"]).mean() * 12)
            metric_rows.append(m)
            if start == periods[0][0]:
                monthly[name] = res["ret"]
                log_trial(f"benchmark_{name}", {"period": f"{start}..{end}"},
                          {k: m[k] for k in ("mean_log_ret_ann", "sharpe", "max_dd")},
                          notes="pre-registered benchmark, EUR after costs and tax")
    metrics = pd.DataFrame(metric_rows)

    RESULTS.mkdir(exist_ok=True)
    pd.DataFrame(monthly).to_csv(RESULTS / "baseline_monthly.csv")
    write_summary(metrics, fc_lines)
    print(f"written {RESULTS / 'baseline_summary.md'}")


def write_summary(metrics: pd.DataFrame, fc_lines: list[str]) -> None:
    lines = [
        "# Baseline results (development period only, holdout 2015+ untouched)",
        "",
        f"Generated by `python -m src.run_baseline`. Research/education, not advice.",
        "",
        "## Forecast: expanding historical mean of log excess return (USD)",
        "",
        "OOS R² and Clark-West are measured against a *zero* equity-premium forecast,",
        "only to check the machinery; from now on the historical mean is the benchmark",
        "that every model must beat. Clark-West uses Newey-West SE (lag h-1, min 1).",
        "",
        "| Horizon | OOS period | N | Latest forecast (ann.) | OOS R² vs 0 | CW t | p (1-sided) |",
        "|---|---|---|---|---|---|---|",
        *fc_lines,
        "",
        "## Benchmark rules: EUR, after costs and Italian tax (liquidated at period end)",
        "",
        "Sharpe is the excess over the EUR return of USD T-bills; its SE ≈ sqrt((1+SR²/2)/years).",
        "`t NW` = Newey-West t-stat (12 lags) of mean monthly log excess return.",
        "",
    ]
    for (start, end), g in metrics.groupby(["start", "end"], sort=False):
        lines += [f"### {start} to {end}", "",
                  "| Rule | Mean log ret | CAGR | Vol | Sharpe (SE) | t NW | Max DD | CVaR 5% (m) | Turnover/yr | Cost+tax drag/yr |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for _, m in g.iterrows():
            flag = " ⚠" if m["max_dd"] > 0.25 else ""
            lines.append(
                f"| {m['rule']} | {m['mean_log_ret_ann']:.2%} | {m['cagr']:.2%} | {m['vol_ann']:.1%} | "
                f"{m['sharpe']:.2f} ({m['sharpe_se']:.2f}) | {m['excess_t_nw']:.2f} | "
                f"{m['max_dd']:.1%}{flag} | {m['cvar5_monthly']:.1%} | {m['turnover_ann']:.2f} | "
                f"{m['drag_ann']:.2%} |")
        lines.append("")
    lines += ["⚠ = breaks the pre-registered 25% max-drawdown limit.", ""]
    (RESULTS / "baseline_summary.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
