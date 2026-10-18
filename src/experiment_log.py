"""Experiment log: one row per trial, appended to experiments/log.csv.

Why: if you try 50 strategy variants and report the best, its Sharpe ratio is inflated
by selection. Counting every trial from day one lets us later compute a Deflated Sharpe
Ratio (Bailey & Lopez de Prado) that corrects for the number of attempts.

Usage:
    from src.experiment_log import log_trial, n_trials
    log_trial("sma10_baseline", params={"window": 10}, metrics={"sharpe": 0.41})
"""
from __future__ import annotations

import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[1] / "experiments" / "log.csv"
FIELDS = ["timestamp_utc", "trial_id", "name", "git_commit", "params", "metrics", "notes"]


def _git_commit() -> str:
    """Short hash of the current commit, so each trial is reproducible."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=LOG_PATH.parents[1],
            stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return "unknown"


def n_trials(path: Path = LOG_PATH) -> int:
    """How many trials have been logged so far."""
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


def log_trial(name: str, params: dict | None = None, metrics: dict | None = None,
              notes: str = "", path: Path = LOG_PATH) -> int:
    """Append one trial and return its sequential id."""
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    trial_id = n_trials(path) + 1
    row = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trial_id": trial_id,
        "name": name,
        "git_commit": _git_commit(),
        "params": json.dumps(params or {}, sort_keys=True, default=str),
        "metrics": json.dumps(metrics or {}, sort_keys=True, default=str),
        "notes": notes,
    }
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(row)
    return trial_id
