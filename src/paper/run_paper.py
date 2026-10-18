"""Paper trading of the final strategy: one run per month, no real money, no broker.

Each run (after a month-end T, once data are downloaded with `python -m src.ingest.run_all`
and `python -m src.ingest.yahoo`):
  1. data-quality checks: stop if an input is stale or implausible (see CHECKS below);
  2. books the paper return of the month just ended, from the weights decided last run;
  3. decides the target weights for the next month with the frozen final strategy;
  4. checks the pre-registered kill criteria on the paper track record.

Live inputs differ from the research data (docs/paper_trading.md):
  * country equities: US-listed country ETFs (Yahoo, yh_*), because the research indexes
    are updated once a year. Spliced after the last research month;
  * OECD 10-year yields appear on FRED with a delay of 1-2 months: a missing month is
    carried forward from the last published yield (flagged "provisional", at most 2).

Files (append-only, committed with the code): paper/decisions.csv, paper/track.csv.

Run:  .venv\\Scripts\\python -m src.paper.run_paper [--T YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.decision import backtest
from src.decision.multi_asset import target_weights
from src.features.returns import returns_panel
from src.features.universe import BONDS, EQUITY, universe_panel
from src.features.valuation import cape_percentile
from src.ingest.store import load_all
from src.run_holdout import FINAL
from src.run_step_d import CAPE_THRESHOLD, NEEDED

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "paper"
LIVE_SERIES = sorted(set(NEEDED + [f"yh_{c}" for c in EQUITY]))
MAX_STALE_MONTHS = 2
MAX_ABS_MONTHLY_RET = 0.30
KILL_DRAWDOWN = 0.25            # hard limit from the objective (section 1)
REVIEW_DRAWDOWN_PCTL = 0.95     # review if paper drawdown > 95th pct of the backtest's


def live_panel(records: pd.DataFrame, T) -> tuple[pd.DataFrame, list[str]]:
    """Universe at T with live proxies spliced in; returns (panel, provisional notes)."""
    T = pd.Timestamp(T)
    ff = records[records["series"].isin(["ff_MKT_RF", "ff_RF"])]
    ff_last = ff.loc[ff["availability_date"] <= T, "observation_date"].max()
    recs = records
    notes = []
    # carry forward missing yields / FX / rates for up to MAX_STALE_MONTHS (provisional)
    keep = records[records["availability_date"] <= T]
    last = keep.groupby("series")["observation_date"].max()
    extra = []
    for s, d in last.items():
        if s.startswith(("fred_IRLTLT01", "fred_IR3TIB01", "fred_CCUSMA02", "fred_GS10",
                         "fred_TB3MS")) and d < T:
            gap = (T.to_period("M") - d.to_period("M")).n
            if gap <= MAX_STALE_MONTHS:
                v = keep.loc[(keep["series"] == s) & (keep["observation_date"] == d), "value"].iloc[-1]
                for k in range(1, gap + 1):
                    obs = (d.to_period("M") + k).to_timestamp(how="end").normalize()
                    extra.append({"series": s, "observation_date": obs, "availability_date": T,
                                  "value": v, "download_ts": pd.Timestamp.max})
                notes.append(f"{s}: last published {d:%Y-%m}, carried forward {gap} month(s)")
    # US equity after French's last month: SPY total return as the CRSP market proxy,
    # T-bill return = previous month's 3m rate / 12
    yh_us = keep[keep["series"] == "yh_US"].set_index("observation_date")["value"]
    tb = keep[keep["series"] == "fred_TB3MS"].set_index("observation_date")["value"]
    for obs, ret in yh_us.items():
        if pd.notna(ff_last) and obs > ff_last:
            prev = (obs.to_period("M") - 1).to_timestamp(how="end").normalize()
            rf = float(tb.get(prev, tb[tb.index <= prev].iloc[-1])) / 12
            extra += [{"series": "ff_RF", "observation_date": obs, "availability_date": obs,
                       "value": rf, "download_ts": pd.Timestamp.max},
                      {"series": "ff_MKT_RF", "observation_date": obs, "availability_date": obs,
                       "value": ret - rf, "download_ts": pd.Timestamp.max}]
    if extra:
        recs = pd.concat([records, pd.DataFrame(extra)], ignore_index=True)
    # US equity: CRSP via French until its last month, then SPY
    u = universe_panel(recs, T)
    fx = returns_panel(recs, T)["fx"]
    fx_ret = (fx / fx.shift(1)).reindex(u.index)
    yh = (recs[(recs["series"].str.startswith("yh_")) & (recs["availability_date"] <= T)]
          .sort_values("download_ts").drop_duplicates(["series", "observation_date"], keep="last")
          .pivot(index="observation_date", columns="series", values="value"))
    for c in EQUITY:
        proxy = ((1 + yh.get(f"yh_{c}", pd.Series(dtype=float)).reindex(u.index)) * fx_ret - 1)
        u[f"eq_{c}"] = u[f"eq_{c}"].combine_first(proxy)
    if pd.notna(ff_last) and ff_last < T:
        notes.append(f"US equity from SPY after {ff_last:%Y-%m}")
    return u, notes


def quality_checks(u: pd.DataFrame, T) -> list[str]:
    """Problems that stop the run (empty list = OK)."""
    T = pd.Timestamp(T)
    problems = []
    if T not in u.index:
        return [f"no data row for {T:%Y-%m}"]
    for c in [f"eq_{x}" for x in EQUITY] + [f"bond_{x}" for x in BONDS] + ["cash"]:
        if pd.isna(u.loc[T, c]):
            problems.append(f"{c}: no value for {T:%Y-%m}")
        elif abs(u.loc[T, c]) > MAX_ABS_MONTHLY_RET:
            problems.append(f"{c}: implausible monthly return {u.loc[T, c]:.1%}")
    return problems


def decide(records: pd.DataFrame, u: pd.DataFrame, T) -> dict[str, float]:
    _, rule, opts = FINAL
    opts = dict(opts)
    if opts.pop("valuation", False):
        opts["equity_scale"] = 0.5 if cape_percentile(records, T) > CAPE_THRESHOLD else 1.0
    return target_weights(u.loc[:pd.Timestamp(T)], rule, "eq", **opts)


def kill_check(track: pd.DataFrame) -> list[str]:
    """Pre-registered kill criteria on the paper track record (after costs, before tax)."""
    if track.empty:
        return []
    wealth = (1 + track["net_ret"]).cumprod()
    dd = float((1 - wealth / wealth.cummax()).max())
    msgs = []
    if dd > KILL_DRAWDOWN:
        msgs.append(f"STOP: paper drawdown {dd:.0%} > {KILL_DRAWDOWN:.0%} limit")
    ref = PAPER / "backtest_drawdown_quantiles.csv"
    if ref.exists():
        q = pd.read_csv(ref, index_col=0)["dd_q95"]
        n = min(len(track), q.index.max())
        if dd > q.loc[n]:
            msgs.append(f"REVIEW: paper drawdown {dd:.0%} above the backtest's 95th percentile "
                        f"for {n} months ({q.loc[n]:.0%})")
    return msgs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--T", help="decision month-end (default: last completed month)")
    T = pd.Timestamp(ap.parse_args().T or pd.Timestamp.today().to_period("M").to_timestamp()
                     - pd.offsets.Day(1)).normalize()
    records = load_all()
    records = records[records["series"].isin(LIVE_SERIES)]
    u, notes = live_panel(records, T)
    problems = quality_checks(u, T)
    if problems:
        raise SystemExit("data-quality check failed, nothing booked:\n  " + "\n  ".join(problems))

    PAPER.mkdir(exist_ok=True)
    dec_path, track_path = PAPER / "decisions.csv", PAPER / "track.csv"
    decisions = pd.read_csv(dec_path, parse_dates=["T"]) if dec_path.exists() else pd.DataFrame()
    track = pd.read_csv(track_path, parse_dates=["month"]) if track_path.exists() else pd.DataFrame()
    if not decisions.empty and (decisions["T"] == T).any():
        raise SystemExit(f"{T:%Y-%m} already decided; nothing to do")

    # 1. book the month just ended with last run's weights
    if not decisions.empty:
        prev_T = decisions["T"].max()
        if (T.to_period("M") - prev_T.to_period("M")).n != 1:
            raise SystemExit(f"last decision {prev_T:%Y-%m}; run the missing months in order")
        w = decisions[decisions["T"] == prev_T].set_index("asset")["weight"]
        r = u.loc[T].rename({"cash": "rf"})
        gross = float(sum(w[a] * r[a] for a in w.index))
        track = pd.concat([track, pd.DataFrame([{"month": T, "gross_ret": gross}])],
                          ignore_index=True)

    # 2. decide next month's weights
    w_new = decide(records, u, T)
    if not decisions.empty:
        w_old = decisions[decisions["T"] == decisions["T"].max()].set_index("asset")["weight"]
        assets = set(w_old.index) | set(w_new)
        cost = sum(abs(w_new.get(a, 0.0) - w_old.get(a, 0.0))
                   * backtest.COST[backtest.asset_class(a)] for a in assets if a != "rf")
        track.loc[track.index[-1], "cost"] = cost
        track.loc[track.index[-1], "net_ret"] = track["gross_ret"].iloc[-1] - cost
    new_rows = pd.DataFrame([{"T": T, "asset": a, "weight": v, "notes": "; ".join(notes)}
                             for a, v in sorted(w_new.items(), key=lambda x: -x[1])])
    pd.concat([decisions, new_rows], ignore_index=True).to_csv(dec_path, index=False)
    track.to_csv(track_path, index=False)

    print(f"decision for {T:%Y-%m} (hold during {(T + pd.offsets.MonthEnd(1)):%Y-%m}):")
    for a, v in sorted(w_new.items(), key=lambda x: -x[1]):
        print(f"  {a:10s} {v:6.1%}")
    for n in notes:
        print(f"  note: {n}")
    for m in kill_check(track.dropna(subset=["net_ret"]) if "net_ret" in track else track):
        print(m)


def drawdown_quantiles(monthly: pd.Series, horizons=range(1, 61), n_boot: int = 5000,
                       seed: int = 0) -> pd.DataFrame:
    """95th percentile of max drawdown over h months, stationary bootstrap of backtest returns."""
    from src.run_step_b import drawdown_rows, stationary_bootstrap
    r = monthly.dropna().to_numpy()
    idx = stationary_bootstrap(len(r), n_boot, 12, np.random.default_rng(seed))
    sims = r[idx[:, :max(horizons)]]
    start = np.zeros((len(sims), 1))  # wealth starts at 1 before the first month
    out = {h: float(np.quantile(drawdown_rows(np.hstack([start, sims[:, :h]])),
                                REVIEW_DRAWDOWN_PCTL)) for h in horizons}
    return pd.DataFrame({"dd_q95": out}).rename_axis("months")


def write_drawdown_reference() -> None:
    """Kill-criterion reference from the development backtest of the final strategy."""
    from src.run_step_b import RESULTS
    m = pd.read_csv(RESULTS / "step_b_monthly.csv", index_col=0, parse_dates=True)
    PAPER.mkdir(exist_ok=True)
    drawdown_quantiles(m["tsmom12 | eq | 1976-01"]).to_csv(
        PAPER / "backtest_drawdown_quantiles.csv", float_format="%.4f")


if __name__ == "__main__":
    main()
