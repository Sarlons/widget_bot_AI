"""The experiment log must count trials sequentially and never overwrite old rows."""
from src.experiment_log import log_trial, n_trials


def test_log_appends_and_counts(tmp_path):
    p = tmp_path / "log.csv"
    assert n_trials(p) == 0
    assert log_trial("a", {"x": 1}, {"sharpe": 0.1}, path=p) == 1
    assert log_trial("b", path=p) == 2
    assert n_trials(p) == 2
