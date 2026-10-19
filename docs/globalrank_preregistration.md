# Pre-registration: global index-ranking model (project 2)

Written **2026-10-19**, before any return statistic of the new markets or of the strategies
below was computed (only the start and end dates of the free files were checked). Plan: `global-ranking-plan/plan.md`
(project library). Lorenzo asked for the analysis to run fully automated, with free data
only, focused on European and major global indexes, and a detailed report at the end.
Research and education only, not financial advice.

## 1. Goal

Each month, rank a universe of country stock indexes by expected return over the next
3 months, hold the top group, and **beat buy-and-hold of the developed world (MSCI World
proxy) in EUR after costs and Italian tax**, with a **maximum drawdown no worse than the
benchmark's**, on the evaluation windows below.

## 2. Honesty about the data periods

- Every year up to 2025 has already been seen in some form: 2015-2025 was project 1's
  holdout, and 2022-2025 is recent memory. **No truly unseen history remains.**
- Development evaluation: **1995-01 to 2021-12** (models train from 1976 onwards).
- Short test: **2022-01 to 2025-12**, run once, at the end of the automated pipeline,
  after the model choice (section 7) has been made on development data only. It is a
  check, not proof. The only fully honest verdict would be forward paper trading, which
  Lorenzo has paused.
- Every variant run is logged in `experiments/log.csv` (names starting `gr_`), and the
  deflated Sharpe ratio uses that count. **Cap: 30 variants** (benchmarks included).

## 3. Universe (free data only, no individual stocks)

Country stock-market total returns in USD (dividends reinvested), converted to EUR as in
project 1, monthly:

- **Europe (14):** Austria, Belgium, Denmark, Finland, France, Germany, Ireland, Italy,
  Netherlands, Norway, Spain, Sweden, Switzerland, UK. Source: Kenneth French
  international country indexes (start 1975-1991 by country).
- **Rest of world (8):** US (CRSP), Japan, Canada, Australia, Hong Kong, Singapore, New
  Zealand, Malaysia (ends 2001: it leaves the universe, as a delisted asset would).
- **Emerging markets** aggregate (French emerging-markets market factor, 1989+).

Individual European stocks are out: free sources only list today's survivors, which
biases a "pick the winners" model. Each index maps to a UCITS ETF an Italian investor can
buy (listed in the report); some smaller countries only have a few such ETFs.

**Benchmark:** developed-world market (French developed-markets market factor, 1990-07+,
a free proxy for MSCI World), buy-and-hold, in EUR.

## 4. Features (price-only, cross-sectional, known at month-end T)

Per index: returns over 1, 3, 6 and 12-1 months (12-1 = months t-12..t-1); distance from
the 12-month high; 12-month volatility; current drawdown from the all-time high; 36-month
correlation with the world benchmark; 12-month trend slope (regression of log index on
time). Each feature is converted to a cross-sectional percentile rank in [0, 1] each month.
An index enters after 36 months of data.

**Label:** cross-sectional percentile rank of the next 3-month return. A model trained at
T only uses labels whose 3-month window ended at least 1 month before T (purge + embargo).

## 5. Strategies

Benchmarks: **W** world buy-and-hold (the target), **US** US buy-and-hold, **EW** equal
weight over all available indexes (rebalanced monthly).

Ranking models (each sets a score per index each month):

1. **M0 momentum:** score = 12-1 month return (no model). The bar every model must clear.
2. **M1 linear:** ridge regression (alpha 1.0) of the label on the ranked features,
   expanding window, refit every month.
3. **M2 trees:** gradient-boosted trees (scikit-learn HistGradientBoosting, the same family
   as LightGBM; max depth 3, learning rate 0.05, 200 iterations, min 50 samples per leaf),
   refit every January on the expanding window.
4. **M3 neural net:** small MLP (one hidden layer of 16), run **only if M2 beats M0** on the
   development window.

**Portfolio rule (all models):** hold the top third by score in equal weight. To limit
turnover and tax, a held index is kept until its score falls out of the top half; weights
are reset to equal only when the holdings change. Fully invested, no leverage, no cash.

## 6. Costs and Italian tax (accumulating UCITS ETFs)

- Trading cost 0.10% of traded value; ETF running cost 0.30% a year for country/EM ETFs,
  0.20% for the world ETF, deducted monthly.
- Accumulating ETFs: no dividend tax while held. Gains on sale are *redditi di capitale*,
  taxed at 26%; **ETF losses are *redditi diversi* and cannot offset ETF gains**, so in an
  ETF-only portfolio they are lost (conservative). Everything is sold at the end of each
  window and taxed.

## 7. Decision rules

- **Development gate (1995-2021):** the chosen model must beat both M0 and W in mean log
  return after costs and tax, with max drawdown no worse than W's, and a deflated Sharpe
  ratio >= 0.95 over all `gr_` trials. If no model passes, the result is "no model beats
  the simple choices" and the short test is still run for M0, M1, M2 (and M3) for
  information.
- **Chosen model:** among those passing the gate, the highest mean log return; ties within
  0.10 pp per year go to the simpler model (M0 < M1 < M2 < M3).
- **Short test (2022-2025):** the chosen model (or, if none passed, all models) is run
  once with the same code; reported against W, US and EW. Nothing is re-tuned after it.

## Changelog

- 2026-10-19: initial version.
