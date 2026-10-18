"""Sanity checks on the power formulas."""
import math

from src.validation.power import min_track_record_years, sharpe_se


def test_sharpe_se_known_value():
    # SR=0 over 1 year -> SE = 1; over 100 years -> 0.1
    assert sharpe_se(0.0, 1) == 1.0
    assert math.isclose(sharpe_se(0.0, 100), 0.1)


def test_mintrl_monotonic():
    assert min_track_record_years(0.4, 0.4) == math.inf
    # a bigger edge needs less data; fat tails need more
    assert min_track_record_years(0.8) < min_track_record_years(0.4)
    assert min_track_record_years(0.4, skew=-0.5, kurt=5) > min_track_record_years(0.4)
