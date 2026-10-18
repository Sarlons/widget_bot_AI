"""Performance metrics and forecast tests.

Strategy metrics (monthly returns):
  mean log return (the objective), CAGR, volatility, Sharpe (with Lo SE), max drawdown,
  CVaR 5%, Newey-West t-stat of mean excess return.

Forecast metrics:
  oos_r2      Campbell-Thompson out-of-sample R2 vs a benchmark forecast
  clark_west  Clark-West (2007) test for nested models, HAC (Newey-West) standard errors
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from src.validation.power import sharpe_se


def nw_mean_test(x: pd.Series, lags: int) -> tuple[float, float]:
    """Mean of x and its Newey-West t-statistic (regression of x on a constant)."""
    x = pd.Series(x).dropna()
    res = sm.OLS(x.to_numpy(), np.ones(len(x))).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    return float(res.params[0]), float(res.tvalues[0])


def max_drawdown(r: pd.Series) -> float:
    wealth = (1 + r).cumprod()
    return float((1 - wealth / wealth.cummax()).max())


def cvar(r: pd.Series, q: float = 0.05) -> float:
    """Average of the worst q fraction of monthly returns (reported as a negative number)."""
    cutoff = r.quantile(q)
    return float(r[r <= cutoff].mean())


def strategy_metrics(r: pd.Series, rf: pd.Series) -> dict:
    r = r.dropna()
    ex = (r - rf.reindex(r.index))
    years = len(r) / 12
    sr = ex.mean() / ex.std() * np.sqrt(12)
    _, t_nw = nw_mean_test(np.log1p(r) - np.log1p(rf.reindex(r.index)), lags=12)
    return {
        "start": r.index[0].strftime("%Y-%m"), "end": r.index[-1].strftime("%Y-%m"),
        "mean_log_ret_ann": float(np.log1p(r).mean() * 12),
        "cagr": float((1 + r).prod() ** (1 / years) - 1),
        "vol_ann": float(r.std() * np.sqrt(12)),
        "sharpe": float(sr),
        "sharpe_se": sharpe_se(sr, years),
        "excess_t_nw": t_nw,
        "max_dd": max_drawdown(r),
        "cvar5_monthly": cvar(r),
    }


def oos_r2(y: pd.Series, f_model: pd.Series, f_bench: pd.Series) -> float:
    """1 - SSE(model)/SSE(benchmark). Positive = model beats the benchmark."""
    return float(1 - ((y - f_model) ** 2).sum() / ((y - f_bench) ** 2).sum())


def clark_west(y: pd.Series, f_model: pd.Series, f_bench: pd.Series, horizon: int) -> dict:
    """Clark-West test: H0 the larger model (f_model) does not improve on f_bench.

    adj_t = (y - f_bench)^2 - [(y - f_model)^2 - (f_bench - f_model)^2]
    Regress adj_t on a constant with Newey-West SE, lag = horizon - 1 (min 1); one-sided.
    """
    from scipy.stats import norm
    adj = (y - f_bench) ** 2 - ((y - f_model) ** 2 - (f_bench - f_model) ** 2)
    mean, t = nw_mean_test(adj, lags=max(1, horizon - 1))
    return {"cw_stat": t, "cw_pvalue": float(1 - norm.cdf(t))}
