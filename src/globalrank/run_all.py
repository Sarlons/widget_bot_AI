"""Project 2, fully automated: data -> features -> models -> backtests -> short test -> report.

    .venv\\Scripts\\python -m src.globalrank.run_all [--no-download]

Steps (docs/globalrank_preregistration.md):
  1. download the free data (unless --no-download) into the point-in-time store;
  2. for every month-end, the panel known at that date and its ranked features;
     labels of month t only from the panel known at t+3 (when they became known);
  3. development 1995-01..2021-12: benchmarks W, US, EW and models M0, M1, M2 (M3 only if
     M2 beats M0), each simulated in EUR with ETF costs and Italian tax, logged as a trial;
  4. development gate and mechanical model choice (section 7);
  5. short test 2022-01..2025-12 with the same code, once;
  6. HTML + Markdown report in results/globalrank/.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.decision import backtest
from src.experiment_log import LOG_PATH, log_trial
from src.globalrank import models
from src.globalrank.data import ASSETS, SERIES, panel_at
from src.globalrank.features import HORIZON, MIN_MONTHS, eligible, features_at, label
from src.ingest.store import load_all
from src.run_step_b import drawdown_rows, stationary_bootstrap
from src.validation.deflated_sharpe import expected_max_sharpe, probabilistic_sharpe
from src.validation.metrics import strategy_metrics

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "globalrank"
DEV = ("1995-01", "2021-12")
TEST = ("2022-01", "2025-12")
FIRST_FEATURE = pd.Timestamp("1977-12-31")
COST = {"etf": 0.0010, "rf": 0.0}
TIE_PP = 0.0010
DSR_BAR = 0.95


def month(s: str, end: bool = True) -> pd.Timestamp:
    return pd.Period(s, "M").to_timestamp(how="end").normalize()


def build(records: pd.DataFrame, last: pd.Timestamp):
    """Point-in-time features of every month and labels from the panel known at t+3."""
    dates = pd.date_range(FIRST_FEATURE, last, freq="ME")
    panels = {t: panel_at(records, t) for t in dates}
    feats = {t: features_at(panels[t], t) for t in dates}
    labels = {}
    for t in dates:
        known = (t.to_period("M") + HORIZON).to_timestamp(how="end").normalize()
        if known in panels and not feats[t].empty:
            labels[t] = label(panels[known], t, feats[t].index.tolist())
    return panels, feats, labels


def simulate(weights: dict, realised: pd.DataFrame, window) -> pd.DataFrame:
    """EUR account with ETF costs and tax; a stopped index is held at its last value."""
    w = pd.DataFrame(weights).T.fillna(0.0)
    w.columns = [f"etf_{c}" for c in w.columns]
    w["rf"] = 0.0
    real = realised.rename(columns=lambda c: f"etf_{c}")
    real = real.reindex(columns=w.columns).fillna(0.0)
    real["rf"] = realised["cash"]
    inc = pd.DataFrame(0.0, index=real.index, columns=w.columns)
    first = month(window[0]) - pd.offsets.MonthEnd(1)
    w = w.loc[(w.index >= first) & (w.index < month(window[1]))]
    return backtest.run(w, real, inc, cost=COST)


def metrics(res: pd.DataFrame, cash: pd.Series) -> dict:
    m = strategy_metrics(res["ret"], cash)
    m["turnover_ann"] = float(res["turnover"].mean() * 12)
    m["drag_ann"] = float((res["gross_ret"] - res["ret"]).mean() * 12)
    return m


def run_window(window, panels, feats, labels, realised, cash, model_names, tag,
               benchmarks: bool = True) -> dict:
    dates = [T for T in pd.date_range(month(window[0]) - pd.offsets.MonthEnd(1),
                                      month(window[1]) - pd.offsets.MonthEnd(1), freq="ME")]
    weights, extra = {}, {}
    if benchmarks:
        weights["W"] = {T: {"WORLD": 1.0} for T in dates}
        weights["US"] = {T: {"US": 1.0} for T in dates}
        weights["EW"] = models.equal_weight(feats, dates)
    for name in model_names:
        sc = models.scores(name, feats, labels, dates)
        hold = models.holdings(sc)
        weights[name] = models.drifted_weights(hold, realised)
        extra[name] = {"holdings": hold, "scores": sc}
    results = {}
    for name, w in weights.items():
        res = simulate(w, realised, window)
        m = metrics(res, cash)
        results[name] = {"res": res, "m": m}
        log_trial(f"gr_{tag}_{name}", {"window": f"{window[0]}..{window[1]}"},
                  {k: m[k] for k in ("mean_log_ret_ann", "sharpe", "max_dd")},
                  notes=f"project 2 {tag}, EUR after ETF costs and tax")
    return {"results": results, "extra": extra, "weights": weights}


def sharpe_diff_vs(a: pd.Series, b: pd.Series, cash: pd.Series) -> tuple[float, list]:
    c = cash.reindex(a.index).to_numpy()
    x, y = a.to_numpy(), b.reindex(a.index).to_numpy()
    idx = stationary_bootstrap(len(x), 10_000, 12, np.random.default_rng(0))

    def sr(r, cc):
        ex = r - cc
        return ex.mean(axis=-1) / ex.std(axis=-1, ddof=1) * np.sqrt(12)

    d = float(sr(x, c) - sr(y, c))
    return d, np.percentile(sr(x[idx], c[idx]) - sr(y[idx], c[idx]), [2.5, 97.5]).tolist()


def dsr_all(results: dict, cash: pd.Series) -> dict:
    log = pd.read_csv(LOG_PATH)
    gr = log[log["name"].str.startswith("gr_")]
    n = len(gr)
    sh = gr["metrics"].map(lambda s: json.loads(s).get("sharpe")).dropna().to_numpy()
    sr0 = expected_max_sharpe(n, np.var(sh, ddof=1) / 12) if len(sh) > 1 else 0.0
    out = {"n_trials": n, "sr0_ann": sr0 * np.sqrt(12)}
    for name, r in results.items():
        ret = r["res"]["ret"]
        out[name] = probabilistic_sharpe(ret - cash.reindex(ret.index), sr0)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true")
    args = ap.parse_args()
    if not args.no_download:
        from src.ingest import fred, french, french_intl, french_regions
        for mod in (fred, french, french_intl, french_regions):
            print(f"{mod.__name__}: {mod.ingest()} new records")

    records = load_all()
    records = records[records["series"].isin(SERIES)]
    last = month(TEST[1])
    print("building point-in-time panels and features ...")
    panels, feats, labels = build(records, last)
    realised = panel_at(records, last + pd.offsets.MonthEnd(1)).loc[:last]
    cash = realised["cash"]
    universe = {c: (realised[c].first_valid_index(), realised[c].last_valid_index())
                for c in ASSETS + ["WORLD"]}

    # ---- development ----
    print("development walk-forward ...")
    dev = run_window(DEV, panels, feats, labels, realised, cash, ["M0", "M1", "M2"], "dev")
    r = dev["results"]
    if r["M2"]["m"]["mean_log_ret_ann"] > r["M0"]["m"]["mean_log_ret_ann"]:
        extra = run_window(DEV, panels, feats, labels, realised, cash, ["M3"], "dev",
                           benchmarks=False)
        r["M3"] = extra["results"]["M3"]
        dev["extra"]["M3"] = extra["extra"]["M3"]
        dev["weights"]["M3"] = extra["weights"]["M3"]
    dsr = dsr_all(r, cash)
    W = r["W"]["m"]
    gate = {}
    for name in [k for k in ("M1", "M2", "M3") if k in r]:
        m = r[name]["m"]
        gate[name] = {
            "beats M0": m["mean_log_ret_ann"] > r["M0"]["m"]["mean_log_ret_ann"],
            "beats W": m["mean_log_ret_ann"] > W["mean_log_ret_ann"],
            "drawdown <= W": m["max_dd"] <= W["max_dd"],
            f"DSR >= {DSR_BAR}": dsr[name] >= DSR_BAR,
        }
    passing = [k for k, g in gate.items() if all(g.values())]
    chosen = None
    if passing:
        best = max(r[k]["m"]["mean_log_ret_ann"] for k in passing)
        chosen = [k for k in passing if r[k]["m"]["mean_log_ret_ann"] >= best - TIE_PP][0]
    diffs = {k: sharpe_diff_vs(v["res"]["ret"], r["W"]["res"]["ret"], cash)
             for k, v in r.items() if k != "W"}

    # ---- short test, once ----
    print("short test 2022-2025 ...")
    test_models = [chosen] if chosen else [k for k in ("M0", "M1", "M2", "M3") if k in r]
    test = run_window(TEST, panels, feats, labels, realised, cash, test_models, "test")
    tdiffs = {k: sharpe_diff_vs(v["res"]["ret"], test["results"]["W"]["res"]["ret"], cash)
              for k, v in test["results"].items() if k != "W"}

    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({k: v["res"]["ret"] for k, v in r.items()}).to_csv(OUT / "dev_monthly.csv")
    pd.DataFrame({k: v["res"]["ret"] for k, v in test["results"].items()}).to_csv(
        OUT / "test_monthly.csv")
    from src.globalrank.report import write_report
    write_report(OUT, universe, dev, test, gate, chosen, dsr, diffs, tdiffs, feats, labels,
                 realised, cash)
    print(f"report: {OUT / 'report.html'}")


if __name__ == "__main__":
    main()
