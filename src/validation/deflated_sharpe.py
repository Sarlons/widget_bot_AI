"""Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014) using the experiment log.

If N strategies are tried and the best is kept, its Sharpe is inflated even when none has
skill. The DSR asks: what is the probability that the true Sharpe is above zero, once we
correct for (a) the number of trials N, (b) the spread of Sharpe ratios across trials and
(c) non-normal returns (skew, fat tails) and track-record length T?

Expected maximum Sharpe of N skill-less trials (per period):
    SR0 = sqrt(V) * ((1 - g) * z(1 - 1/N) + g * z(1 - 1/(N e))),   g = 0.5772 (Euler)
where V is the variance of the trials' Sharpe estimates. Then
    DSR = Phi( (SR - SR0) * sqrt(T - 1) / sqrt(1 - skew*SR + (kurt - 1)/4 * SR^2) )
with SR, skew, kurt (not excess) of the strategy's monthly excess returns.
DSR > 0.95: the Sharpe survives the deflation at the 5% level.

Run:  .venv\\Scripts\\python -m src.validation.deflated_sharpe
Output: results/deflated_sharpe.md (no trial is logged: this is a check, not a strategy)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

from src.experiment_log import LOG_PATH

EULER = 0.5772156649015329
RESULTS = Path(__file__).resolve().parents[2] / "results"


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """SR0: expected maximum of n_trials Sharpe estimates with zero true Sharpe (per period)."""
    if n_trials < 2:
        return 0.0
    return math.sqrt(var_sr) * ((1 - EULER) * norm.ppf(1 - 1 / n_trials)
                                + EULER * norm.ppf(1 - 1 / (n_trials * math.e)))


def probabilistic_sharpe(excess: pd.Series, sr0: float) -> float:
    """P(true per-period Sharpe > sr0) given the sample of monthly excess returns."""
    x = pd.Series(excess).dropna().to_numpy()
    sr = x.mean() / x.std(ddof=1)
    g3, g4 = skew(x), kurtosis(x, fisher=False)
    return float(norm.cdf((sr - sr0) * math.sqrt(len(x) - 1)
                          / math.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)))


def trial_sharpes(path: Path = LOG_PATH) -> tuple[int, int, np.ndarray]:
    """(all trials, distinct configurations, annualised Sharpe of distinct configurations).

    A configuration = trial name + params; re-runs of the same configuration at a later
    commit count as trials in N_all but only once in the Sharpe variance.
    """
    log = pd.read_csv(path)
    log["sharpe"] = log["metrics"].map(lambda m: json.loads(m).get("sharpe"))
    distinct = log.drop_duplicates(["name", "params"], keep="last")
    return len(log), len(distinct), distinct["sharpe"].dropna().to_numpy()


def main() -> None:
    from src.features.universe import SERIES, universe_panel
    from src.ingest.store import load_all
    from src.validation.walkforward import DEV_END, assert_no_holdout

    records = load_all()
    cash = universe_panel(records[records["series"].isin(SERIES)], DEV_END)["cash"]
    monthly = pd.read_csv(RESULTS / "step_b_monthly.csv", index_col=0, parse_dates=True)
    assert_no_holdout(monthly.index)

    n_all, n_distinct, sharpes = trial_sharpes()
    var_m = np.var(sharpes, ddof=1) / 12  # variance of per-month Sharpe across trials
    cases = {"all logged trials": n_all, "distinct configurations": n_distinct}
    sr0 = {k: expected_max_sharpe(n, var_m) for k, n in cases.items()}

    lines = [
        "# Deflated Sharpe Ratio (development period)",
        "",
        "Probability that the true Sharpe (vs EUR cash, after costs and tax) is above zero,",
        "after correcting for the number of strategies tried, the spread of their Sharpe",
        "ratios and non-normal returns (Bailey & Lopez de Prado 2014). DSR > 0.95 = survives.",
        "",
        f"- Trials in `experiments/log.csv`: **{n_all}** ({n_distinct} distinct configurations;",
        "  re-runs of the same benchmark at later commits counted separately in the first number).",
        f"- Std of annualised Sharpe across the {len(sharpes)} distinct strategy trials: "
        f"{math.sqrt(var_m * 12):.3f}.",
        f"- Sharpe that the best of N skill-less trials would reach by luck (annualised): "
        f"**{sr0['all logged trials'] * math.sqrt(12):.2f}** with N = {n_all}, "
        f"{sr0['distinct configurations'] * math.sqrt(12):.2f} with N = {n_distinct}.",
        "",
        "| Strategy | Window | Sharpe | Skew | Kurtosis | PSR (vs 0) | DSR, N all | DSR, N distinct |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for col in monthly.columns:
        rule, sleeve, start = (s.strip() for s in col.split("|"))
        r = monthly[col].dropna()
        ex = r - cash.reindex(r.index)
        sr = ex.mean() / ex.std(ddof=1)
        lines.append(
            f"| {rule} ({'hedged' if sleeve == 'eqh' else 'unhedged'}) | "
            f"{r.index[0]:%Y-%m}..{r.index[-1]:%Y-%m} | {sr * math.sqrt(12):.2f} | "
            f"{skew(ex):.2f} | {kurtosis(ex, fisher=False):.1f} | "
            f"{probabilistic_sharpe(ex, 0.0):.3f} | "
            f"{probabilistic_sharpe(ex, sr0['all logged trials']):.3f} | "
            f"{probabilistic_sharpe(ex, sr0['distinct configurations']):.3f} |")
    lines += [
        "",
        "Caveats: the trials are strongly correlated (same markets, overlapping windows), so",
        "N overstates the number of independent tries and the DSR is conservative. The",
        "variance of trial Sharpes mixes different windows. Holdout 2015+ untouched.",
        "",
    ]
    (RESULTS / "deflated_sharpe.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"written {RESULTS / 'deflated_sharpe.md'}")


if __name__ == "__main__":
    main()
