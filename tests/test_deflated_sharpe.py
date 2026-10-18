"""Checks of the Deflated Sharpe Ratio formulas."""
import math

import numpy as np
import pandas as pd
from scipy.stats import norm

from src.validation.deflated_sharpe import EULER, expected_max_sharpe, probabilistic_sharpe


def test_expected_max_sharpe_formula_and_monotone():
    assert expected_max_sharpe(1, 0.01) == 0.0
    assert math.isclose(expected_max_sharpe(2, 0.04), 0.2 * EULER * norm.ppf(1 - 1 / (2 * math.e)))
    assert expected_max_sharpe(10, 0.01) < expected_max_sharpe(100, 0.01)


def test_expected_max_matches_simulation():
    rng = np.random.default_rng(0)
    sims = rng.normal(0, 0.1, (20_000, 50)).max(axis=1).mean()
    assert abs(expected_max_sharpe(50, 0.01) - sims) < 0.01


def test_psr_normal_returns_matches_simple_formula():
    rng = np.random.default_rng(1)
    x = pd.Series(rng.normal(0.01, 0.05, 5000))
    sr = x.mean() / x.std(ddof=1)
    assert abs(probabilistic_sharpe(x, 0.0) - norm.cdf(sr * math.sqrt(4999) / math.sqrt(1 + sr**2 / 2))) < 0.01
    assert probabilistic_sharpe(x, sr + 0.05) < 0.5 < probabilistic_sharpe(x, sr - 0.05)
