# mercatifinanziari: quantitative market research (education/research, not advice)

Rules for the project: see `CLAUDE.md`. Plan and fixed targets: `docs/preregistration.md`.

## Quick start (Windows)

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m src.ingest.run_all      # download data (Shiller, FRED, French)
.venv\Scripts\python -m pytest -q               # tests, incl. the leakage test
.venv\Scripts\python -m src.run_baseline        # step 4: baseline -> results/baseline_summary.md
.venv\Scripts\python -m src.validation.power    # how much data is needed to trust a Sharpe
```

In PyCharm: open this folder, Settings > Project > Python Interpreter > Add > Existing,
choose `.venv\Scripts\python.exe`.

## Map

| Path | What it does |
|---|---|
| `src/ingest/store.py` | point-in-time store; `as_of(records, T)` = what was known at T |
| `src/ingest/shiller.py`, `fred.py`, `french.py` | downloaders, publication lags |
| `src/features/returns.py` | monthly total returns (USD and EUR) + EUR cash, known at T |
| `src/features/universe.py` | 11 equity + 11 bond markets in EUR, known at T |
| `src/ingest/french_intl.py` | French international country indexes |
| `src/run_universe_summary.py` | describes the universe -> results/universe_summary.md |
| `src/decision/multi_asset.py` | step-B rules: TSMOM-12, SMA-10, risk weighting, benchmarks 5-6 |
| `src/run_step_b.py` | step B + hedge test H -> results/step_b_summary.md |
| `src/ingest/worldbank.py`, `src/run_step_c.py` | gold prices; step C (currencies + gold) -> results/step_c_summary.md |
| `src/validation/deflated_sharpe.py` | Deflated Sharpe Ratio over all logged trials -> results/deflated_sharpe.md |
| `src/models/historical_mean.py` | baseline forecast every model must beat |
| `src/decision/benchmarks.py` | the 4 benchmark rules |
| `src/decision/backtest.py` | EUR account with costs and Italian taxes |
| `src/validation/` | walk-forward dates, metrics, Clark-West, power analysis |
| `src/run_baseline.py` | runs step 4 end to end |
| `experiments/log.csv` | every trial ever run (for Sharpe deflation) |
