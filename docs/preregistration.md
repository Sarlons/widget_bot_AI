# Pre-registration

Written **2026-10-18**, before any model has been fitted or any out-of-sample result seen.
Purpose: fix the objective, benchmarks, metrics and labels *in advance*, so later results
cannot be tuned to look good. Any change must be appended to the changelog at the bottom
with date and reason. Research/education only; not financial advice.

## 1. Objective

Maximise **long-run growth of wealth**, measured as the **mean monthly log return** of the
portfolio, **in EUR, after transaction costs and Italian 26% tax on realised gains**,
subject to a **maximum drawdown of 25%** over the evaluation period.

A strategy that violates the drawdown limit is rejected regardless of its growth.

Investor assumptions (fixed):
- Base currency EUR; USD assets unhedged unless a rule says otherwise (EUR/USD from FRED).
- Universe for phase 1: US equity (S&P 500 total return) and cash/bonds (T-bill, 10y Treasury).
- Transaction cost: 10 bp per unit of turnover (one-way) for equity, 5 bp for bonds/T-bills.
- Tax: 26% on realised net gains (12.5% on government bonds), losses carried forward
  4 years (Italian *regime amministrato* approximation); tax applied at each sale.
- Rebalancing at month-end close, using only data available at that close.

## 2. Three time levels

| Level | Horizon | Role | Inputs (candidates) | Output |
|---|---|---|---|---|
| Strategic | 3–5 years | Long-run equity weight range | Valuation: CAPE, earnings/dividend yield, excess CAPE yield | Allowed equity range, e.g. 30–100% |
| Tactical | 1–12 months | Tilt inside the strategic range | Trend (10-month SMA, 12-1 momentum), macro (term spread, credit spread, unemployment trend, inflation) | Target equity weight |
| Risk | Weekly | Position sizing | Realised / GARCH volatility | Scale exposure to target vol (10% annual), cap leverage at 1.0 |

The levels are applied in order: strategic range -> tactical weight clipped to the range ->
risk scaling.

## 3. Benchmarks (all in EUR, after costs and tax)

1. **Buy-and-hold S&P 500 total return** (100% equity).
2. **60/40**: 60% S&P 500 TR, 40% 10-year Treasury, rebalanced monthly.
3. **Vol-targeted buy-and-hold**: equity weight = min(1, 10% / trailing 12-month realised vol), rest in T-bills.
4. **10-month SMA rule** (Faber): 100% equity if month-end price > 10-month SMA, else T-bills.

## 4. Data periods

- **Development (in-sample + walk-forward OOS):** start of data (Shiller 1871) to **2014-12-31**.
  First OOS forecast no earlier than 1927-01 (≥ 20 years of training data from Shiller,
  1927 is also the start of French factors).
- **Locked holdout:** **2015-01-01 to today**. Touched exactly once, for the final test of
  the strategies selected on the development period. No plots, no metrics before that.

## 5. Primary metrics

Forecast quality (for return forecasts):
- **Out-of-sample R²** vs the expanding historical mean (Campbell & Thompson 2008):
  R²_OS = 1 − Σ(r − r̂_model)² / Σ(r − r̂_mean)².
- **Clark-West (2007) test** of equal predictive accuracy for nested models,
  HAC (Newey-West) standard errors with lag = horizon − 1 (min 1).

Strategy quality (monthly returns, EUR, after costs and tax):
- **Sharpe ratio** (excess over T-bill, annualised) with SE from Lo (2002)/Mertens.
- **Maximum drawdown** (constraint: ≤ 25%).
- **CVaR 5%** (expected shortfall of monthly returns).
- Secondary: mean log return (the objective), CAGR, turnover, Deflated Sharpe Ratio using
  the trial count in `experiments/log.csv`.

## 6. Labels (thresholds fixed now)

All labels use **forward** returns, so they are only known after the horizon has passed;
a model trained at T may only use labels whose horizon ended by T (purging).

| Label | Definition | Horizon | Threshold |
|---|---|---|---|
| `fwd_ret_1m` | Log total return of S&P 500 in excess of T-bill, next month | 1m | continuous |
| `fwd_ret_12m` | Same, next 12 months | 12m | continuous |
| `up_12m` | 1 if `fwd_ret_12m` > 0 | 12m | 0 |
| `crash_12m` | 1 if max drawdown of S&P 500 TR in next 12 months > **20%** | 12m | 20% |
| `fwd_ret_5y` | Annualised real log total return, next 60 months (strategic) | 60m | continuous |
| `bear_regime` | 1 if price is > **20%** below its prior peak (filtered: uses data up to t only) | 0 | 20% |

Overlapping labels (12m, 60m sampled monthly) → HAC/Hansen-Hodrick SE or block bootstrap
with block length ≥ horizon.

## 7. Statistical power (see `src/validation/power.py`)

The SE of an annualised Sharpe ratio estimated from Y years of i.i.d. returns is
approximately sqrt((1 + SR²/2) / Y). With ~88 years of development OOS data (1927–2014),
SE ≈ 0.11 at SR = 0.4, so a Sharpe *difference* of ~0.2 between two strategies is near
the limit of detectability. On the ~11-year holdout, SE ≈ 0.31: the holdout can only
reject large failures, not confirm small edges. Results are interpreted with this in mind.

## Changelog

- 2026-10-18: initial version.
