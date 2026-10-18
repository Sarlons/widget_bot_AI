"""Leakage test: the future must not influence anything computed at date T.

Method: take the data store, replace every value that became available AFTER T with
random garbage, and recompute. Anything computed "as of T" must be identical.
If a function secretly peeks at future data, the garbage changes its output and the
test fails.

Runs on synthetic data always, and on the real store when it has been downloaded.
"""
import numpy as np
import pandas as pd
import pytest

from src.features.returns import returns_panel
from src.ingest.store import PIT_DIR, as_of, load_all

T_DATES = ["1950-06-30", "1987-10-31", "2008-09-30", "2014-12-31"]


def poison_after(records: pd.DataFrame, T, seed: int = 0) -> pd.DataFrame:
    """Copy of records where everything available after T is replaced by garbage."""
    rng = np.random.default_rng(seed)
    out = records.copy()
    future = out["availability_date"] > pd.Timestamp(T)
    out.loc[future, "value"] = rng.normal(0, 1e3, future.sum())
    return out


def synthetic_records() -> pd.DataFrame:
    """Small fake store with the same series names as the real one."""
    obs = pd.date_range("1920-01-31", "2020-12-31", freq="ME")
    rng = np.random.default_rng(1)
    rows = []
    for s, lag, base in [("ff_MKT_RF", 0, 0.005), ("ff_RF", 0, 0.003), ("shiller_rate", 0, 0.05),
                         ("fred_GS10", 0, 0.05), ("fred_CCUSMA02DEM618N", 0, 1.5),
                         ("fred_DEXUSEU", 0, 1.1), ("shiller_E", 6, 10.0)]:
        v = base + rng.normal(0, base * 0.1, len(obs))
        avail = (obs.to_period("M") + lag).to_timestamp(how="end").normalize()
        rows.append(pd.DataFrame({"series": s, "observation_date": obs,
                                  "availability_date": avail, "value": v}))
    df = pd.concat(rows, ignore_index=True)
    df["download_ts"] = pd.Timestamp("2026-01-01")
    return df


def real_records():
    if not any(PIT_DIR.glob("*.parquet")):
        pytest.skip("real data not downloaded (run python -m src.ingest.run_all)")
    return load_all()


@pytest.mark.parametrize("source", ["synthetic", "real"])
@pytest.mark.parametrize("T", T_DATES)
def test_as_of_and_returns_ignore_future(source, T):
    records = synthetic_records() if source == "synthetic" else real_records()
    poisoned = poison_after(records, T)
    pd.testing.assert_frame_equal(as_of(records, T), as_of(poisoned, T))
    pd.testing.assert_frame_equal(returns_panel(records, T), returns_panel(poisoned, T))


def test_poison_actually_changes_future():
    """Guard against a vacuous test: the poisoned store must differ after T."""
    records = synthetic_records()
    T = "1987-10-31"
    poisoned = poison_after(records, T)
    assert not as_of(records, "2020-12-31").equals(as_of(poisoned, "2020-12-31"))


def test_lagged_series_hidden_until_available():
    """shiller_E has a 6-month lag: at T its last observation must be T - 6 months."""
    r = synthetic_records()
    last = as_of(r, "2000-12-31", ["shiller_E"])["shiller_E"].dropna().index.max()
    assert last == pd.Timestamp("2000-06-30")


@pytest.mark.parametrize("T", ["1950-06-30", "2008-09-30"])
def test_baseline_decisions_ignore_future(T):
    """Forecasts and benchmark weights decided at T must not change if the future is garbage."""
    from src.run_baseline import NEEDED, decide_at
    records = real_records()
    records = records[records["series"].isin(NEEDED)]
    a = decide_at(records, T)
    b = decide_at(poison_after(records, T), T)
    assert a == b


@pytest.mark.parametrize("T", ["1980-06-30", "2008-09-30", "2014-12-31"])
def test_universe_ignores_future(T):
    """Multi-asset EUR returns at T must not depend on anything published after T."""
    from src.features.universe import SERIES, universe_panel
    records = real_records()
    records = records[records["series"].isin(SERIES)]
    pd.testing.assert_frame_equal(universe_panel(records, T),
                                  universe_panel(poison_after(records, T), T))


@pytest.mark.parametrize("T", ["1983-12-31", "2008-09-30"])
def test_step_b_decisions_ignore_future(T):
    """Step-B weights (unhedged and hedged) and income decided at T ignore the future."""
    from src.run_step_b import NEEDED, decide_at
    records = real_records()
    records = records[records["series"].isin(NEEDED)]
    assert decide_at(records, T) == decide_at(poison_after(records, T), T)
