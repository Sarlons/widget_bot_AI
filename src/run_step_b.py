"""Step B: multi-asset trend rules, benchmarks 5-6 and the currency-hedge test H.

For every month-end T of the development period (never the 2015+ holdout):
  1. read the universe known at T (universe_panel -> as_of),
  2. compute target weights of every rule, unhedged and hedged equity sleeve,
  3. income yields for the tax accounting (known at T),
then simulate each rule in EUR after costs and Italian tax (src/decision/backtest.py).

Pre-registered in docs/preregistration.md sections 8-10:
  * step B, window 1976-01 to 2014-12: tsmom12, sma10, eq_risk (benchmark 6),
    global_60_40 (benchmark 5), unhedged equities;
  * test H, window 1983-01 to 2014-12: eq_risk, tsmom12, sma10 and US buy-and-hold,
    each hedged vs unhedged; paired stationary bootstrap of the Sharpe difference.

Run:  .venv\\Scripts\\python -m src.run_step_b
Outputs: results/step_b_summary.md, results/step_b_monthly.csv, experiments/log.csv
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.decision import backtest
from src.decision.multi_asset import RULES, target_weights, us_buy_hold
from src.experiment_log import log_trial
from src.features.returns import returns_panel
from src.features.universe import BONDS, SERIES, universe_panel
from src.ingest.store import as_of, load_all
from src.validation.metrics import max_drawdown, strategy_metrics
from src.validation.walkforward import DEV_END, assert_no_holdout, month_ends

RESULTS = Path(__file__).resolve().parents[1] / "results"
NEEDED = sorted(set(SERIES + ["shiller_D", "shiller_P", "fred_GS10"]))
STEP_B = ("1976-01", "2014-12")
TEST_H = ("1983-01", "2014-12")
H_STRATEGIES = ("eq_risk", "tsmom12", "sma10", "us_buy_hold")
COST = dict(backtest.COST, rf=0.0)  # EUR cash is a deposit: no cost
N_BOOT, BLOCK, SEED = 10_000, 12, 0


def bond_yield_col(c: str) -> str:
    return "fred_GS10" if c == "US" else f"fred_IRLTLT01{c}M156N"


def decide_at(records: pd.DataFrame, T) -> dict:
    """Everything decided at month-end T, using only data available at T."""
    u = universe_panel(records, T)
    out = {}
    for sleeve in ("eq", "eqh"):
        for rule in RULES:
            out[(rule, sleeve)] = target_weights(u, rule, sleeve)
        out[("us_buy_hold", sleeve)] = us_buy_hold(sleeve)
    dp = as_of(records, T, ["shiller_D", "shiller_P"]).ffill().iloc[-1]
    y = as_of(records, T, [bond_yield_col(c) for c in BONDS]).ffill().iloc[-1]
    out["income"] = {"eq": dp["shiller_D"] / dp["shiller_P"] / 12,
                     **{f"bond_{c}": y[bond_yield_col(c)] / 12 for c in BONDS
                        if pd.notna(y[bond_yield_col(c)])}}  # markets not live yet: none
    return out


def stationary_bootstrap(n: int, n_boot: int, block: float, rng) -> np.ndarray:
    """Politis-Romano index matrix (n_boot x n): blocks of geometric length, mean `block`."""
    idx = np.empty((n_boot, n), dtype=int)
    idx[:, 0] = rng.integers(0, n, n_boot)
    new = rng.random((n_boot, n)) < 1 / block
    starts = rng.integers(0, n, (n_boot, n))
    for t in range(1, n):
        idx[:, t] = np.where(new[:, t], starts[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def sharpe(r: np.ndarray, cash: np.ndarray) -> np.ndarray:
    ex = r - cash
    return ex.mean(axis=-1) / ex.std(axis=-1, ddof=1) * np.sqrt(12)


def drawdown_rows(r: np.ndarray) -> np.ndarray:
    w = np.cumprod(1 + r, axis=-1)
    return (1 - w / np.maximum.accumulate(w, axis=-1)).max(axis=-1)


def test_h(hedged: pd.Series, unhedged: pd.Series, cash: pd.Series) -> dict:
    """Paired stationary bootstrap of Sharpe(hedged) - Sharpe(unhedged) and max-DD difference."""
    h, u, c = hedged.to_numpy(), unhedged.to_numpy(), cash.reindex(hedged.index).to_numpy()
    d = float(sharpe(h, c) - sharpe(u, c))
    dd = float(max_drawdown(hedged) - max_drawdown(unhedged))
    idx = stationary_bootstrap(len(h), N_BOOT, BLOCK, np.random.default_rng(SEED))
    d_star = sharpe(h[idx], c[idx]) - sharpe(u[idx], c[idx])
    dd_star = drawdown_rows(h[idx]) - drawdown_rows(u[idx])
    return {"sharpe_diff": d, "p_value": float(np.mean(np.abs(d_star - d) >= abs(d))),
            "sharpe_diff_ci": np.percentile(d_star, [2.5, 97.5]).tolist(),
            "max_dd_diff": dd, "max_dd_diff_ci": np.percentile(dd_star, [2.5, 97.5]).tolist()}


def simulate(rows: dict, key, window, realised, income, hedge_pnl) -> pd.DataFrame:
    first_T = pd.Timestamp(window[0]) - pd.offsets.MonthEnd(1)
    dates = [T for T in rows if first_T <= T < pd.Timestamp(window[1]) + pd.offsets.MonthEnd(0)]
    w = pd.DataFrame({T: rows[T][key] for T in dates}).T.fillna(0.0)
    w = w[[c for c in w.columns if c != "rf"] + ["rf"]]
    nxt = [(T.to_period("M") + 1).to_timestamp(how="end").normalize() for T in w.index]
    held = realised.reindex(nxt)[w.columns].to_numpy()
    if np.isnan(held[w.to_numpy() > 0]).any():
        raise RuntimeError(f"{key}: weight on a market without next-month return")
    real = realised.reindex(columns=w.columns).fillna(0.0)
    inc = income.reindex(columns=w.columns).fillna(0.0)
    hp = hedge_pnl[[c for c in hedge_pnl.columns if c in w.columns]]
    return backtest.run(w, real, inc, cost=COST, hedge_pnl=hp if key[1] == "eqh" else None)


def main() -> None:
    records = load_all()
    records = records[records["series"].isin(NEEDED)]
    decisions = month_ends(pd.Timestamp(STEP_B[0]) - pd.offsets.MonthEnd(1),
                           DEV_END - pd.offsets.MonthEnd(1))
    assert_no_holdout(decisions)
    print(f"walk-forward over {len(decisions)} month-ends ...")
    rows = {T: decide_at(records, T) for T in decisions}

    # realised returns of the development period (all known at DEV_END)
    realised = universe_panel(records, DEV_END)
    realised = realised[realised.index <= DEV_END]
    assert_no_holdout(realised.index)
    realised["rf"] = realised["cash"]
    usd_tbill = returns_panel(records, DEV_END)["rf"]  # EUR return of USD T-bills
    hedge_pnl = pd.DataFrame({c: realised[c] - realised["eq_" + c[4:]]
                              for c in realised.columns if c.startswith("eqh_")})

    # income yields of month t+1 are those known at t
    inc = pd.DataFrame({T: rows[T]["income"] for T in decisions}).T
    inc.index = [(T.to_period("M") + 1).to_timestamp(how="end").normalize() for T in inc.index]
    income = pd.DataFrame(index=inc.index)
    for col in realised.columns:
        if col.startswith(("eq_", "eqh_")):
            income[col] = inc["eq"]
        elif col.startswith("bond_"):
            income[col] = inc[col]
    income["rf"] = realised["rf"].reindex(income.index)

    monthly, metric_rows, h_rows = {}, [], []

    def record(key, window, res, note):
        m = strategy_metrics(res["ret"], realised["rf"])
        m_usd = strategy_metrics(res["ret"], usd_tbill)
        m.update(rule=key[0], sleeve=key[1], window=f"{window[0]}..{window[1]}",
                 sharpe_vs_usd_tbill=m_usd["sharpe"], turnover_ann=res["turnover"].mean() * 12,
                 drag_ann=(res["gross_ret"] - res["ret"]).mean() * 12)
        metric_rows.append(m)
        monthly[f"{key[0]} | {key[1]} | {window[0]}"] = res["ret"]
        log_trial(f"stepb_{key[0]}_{key[1]}", {"window": m["window"], "cash": "EUR cash"},
                  {k: m[k] for k in ("mean_log_ret_ann", "sharpe", "max_dd")}, notes=note)

    for rule in RULES:
        key = (rule, "eq")
        record(key, STEP_B, simulate(rows, key, STEP_B, realised, income, hedge_pnl),
               "pre-registered step B, EUR after costs and tax")

    for strat in H_STRATEGIES:
        res = {}
        for sleeve in ("eq", "eqh"):
            key = (strat, sleeve)
            res[sleeve] = simulate(rows, key, TEST_H, realised, income, hedge_pnl)
            record(key, TEST_H, res[sleeve], "pre-registered test H, EUR after costs and tax")
        t = test_h(res["eqh"]["ret"], res["eq"]["ret"], realised["rf"])
        t["strategy"] = strat
        t["hedged_max_dd"] = max_drawdown(res["eqh"]["ret"])
        h_rows.append(t)

    RESULTS.mkdir(exist_ok=True)
    pd.DataFrame(monthly).to_csv(RESULTS / "step_b_monthly.csv", float_format="%.6f")
    write_summary(pd.DataFrame(metric_rows), h_rows)
    print(f"written {RESULTS / 'step_b_summary.md'}")


def write_summary(metrics: pd.DataFrame, h_rows: list[dict]) -> None:
    names = {"tsmom12": "TSMOM-12", "sma10": "SMA-10", "eq_risk": "Equal-risk, no filter (B6)",
             "global_60_40": "Global 60/40 (B5)", "us_buy_hold": "US buy-and-hold"}
    lines = [
        "# Step B: multi-asset rules and currency-hedge test (development period)",
        "",
        "EUR, after costs and Italian tax, liquidated at the end of each window. Monthly",
        "rebalancing, long-only, rest in EUR cash. Sharpe is the excess over EUR cash; its",
        "SE ≈ sqrt((1+SR²/2)/years). `Sharpe vs USD T-bill (comparison)` is for reference only.",
        "Holdout 2015+ untouched. Rules fixed in docs/preregistration.md sections 8-10.",
        "",
    ]
    header = ["| Rule | Equity | Mean log ret | CAGR | Vol | Sharpe (SE) | Sharpe vs USD T-bill "
              "(comparison) | Max DD | CVaR 5% (m) | Turnover/yr | Cost+tax drag/yr |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for window, g in metrics.groupby("window", sort=False):
        title = "Step B" if window.startswith(STEP_B[0]) else "Test H runs"
        lines += [f"## {title}: {window}", ""] + header
        for _, m in g.iterrows():
            flag = " ⚠" if m["max_dd"] > 0.25 else ""
            lines.append(
                f"| {names[m['rule']]} | {'hedged' if m['sleeve'] == 'eqh' else 'unhedged'} | "
                f"{m['mean_log_ret_ann']:.2%} | {m['cagr']:.2%} | {m['vol_ann']:.1%} | "
                f"{m['sharpe']:.2f} ({m['sharpe_se']:.2f}) | {m['sharpe_vs_usd_tbill']:.2f} | "
                f"{m['max_dd']:.0%}{flag} | {m['cvar5_monthly']:.1%} | {m['turnover_ann']:.2f} | "
                f"{m['drag_ann']:.2%} |")
        lines.append("")
    lines += ["⚠ = breaches the 25% drawdown limit (rejected under the pre-registered objective).",
              "",
              f"## Test H: hedged minus unhedged ({TEST_H[0]}..{TEST_H[1]})",
              "",
              f"Paired stationary bootstrap, mean block {BLOCK} months, {N_BOOT:,} draws.",
              "Decision rule: hedged replaces unhedged only if its Sharpe is higher with",
              "p < 0.05 and its max drawdown is within 25%.",
              "",
              "| Strategy | Sharpe diff | 95% CI | p | Max DD diff | 95% CI | Hedged adopted? |",
              "|---|---|---|---|---|---|---|"]
    for t in h_rows:
        adopt = t["sharpe_diff"] > 0 and t["p_value"] < 0.05 and t["hedged_max_dd"] <= 0.25
        lines.append(
            f"| {names[t['strategy']]} | {t['sharpe_diff']:+.2f} | "
            f"[{t['sharpe_diff_ci'][0]:+.2f}, {t['sharpe_diff_ci'][1]:+.2f}] | {t['p_value']:.3f} | "
            f"{t['max_dd_diff']:+.0%} | [{t['max_dd_diff_ci'][0]:+.0%}, {t['max_dd_diff_ci'][1]:+.0%}] | "
            f"{'yes' if adopt else 'no'} |")
    lines += ["",
              "Limits: bond returns are modelled from monthly-average yields; FX for bonds and",
              "for the hedged local returns uses OECD monthly averages; foreign dividend tax uses",
              "the US dividend yield as proxy; US withholding and foreign withholding ignored.",
              ""]
    (RESULTS / "step_b_summary.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
