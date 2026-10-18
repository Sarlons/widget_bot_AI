# Mercati finanziari: quantitative research project

Research and education project. **Nothing here is financial advice.** No real brokerage,
no paid services, no credentials in the repo.

## Non-negotiable rules

1. **No look-ahead.** A forecast made at date T may only use data whose
   `availability_date <= T`. Always query data through `src.ingest.store.as_of(...)`.
2. **Fit preprocessing only in the training window.** Scalers, PCA, imputation,
   winsorization limits, regime models: fitted on data available up to T, then applied.
3. **Publication lags are documented** for every series/feature in `docs/data_lags.md`
   and encoded in the ingest scripts.
4. **Walk-forward only.** Expanding (or rolling) windows in time order. Never random
   train/test splits, never K-fold without purging and embargo.
5. **Locked holdout: 2015-01-01 to today.** Never evaluated, plotted or peeked at until
   the single final test. Development evaluation stops at 2014-12-31
   (`src.validation.walkforward.HOLDOUT_START`).
6. **Regime models use filtered probabilities** (P(state_t | data up to t)), never
   smoothed ones (which use future data).
7. **Overlapping labels** (e.g. 12-month returns sampled monthly): inference uses HAC
   standard errors (Newey-West / Hansen-Hodrick, lag >= horizon-1) or block bootstrap.
8. **Report results in EUR, after transaction costs and Italian 26% capital-gains tax.**
9. **Log every trial** in `experiments/log.csv` via `src.experiment_log.log_trial`,
   including failed ones. The number of trials is used to deflate Sharpe ratios.
10. Pre-registered objective, benchmarks, metrics and label thresholds live in
    `docs/preregistration.md`; changes must be dated and justified there, not silent.

## Layout

- `src/ingest/`: downloaders (raw files saved unmodified) + point-in-time store
- `src/features/`: features built only from `as_of` data
- `src/models/`: forecasting models
- `src/validation/`: walk-forward splitter, metrics, HAC inference, Clark-West
- `src/decision/`: rules that turn forecasts into positions; costs, taxes
- `tests/`: incl. the leakage test (`tests/test_leakage.py`)
- `experiments/log.csv`: every trial ever run

## Environment

Python venv in `.venv` (Python 3.14; Anaconda not installed on this machine).
Run tests: `.venv\Scripts\python -m pytest -q`
