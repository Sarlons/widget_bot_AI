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

## 8. Amendment A: multi-asset universe and EUR cash (2026-10-18)

Decided by Lorenzo on 2026-10-18 ("go with A"), after seeing only the US-only baseline
of step 4, and **before** any statistic of the assets below has been computed.

**Cash leg.** From now on "cash" is a **EUR short-term rate**: the German 3-month rate
(OECD/FRED `IR3TIB01DEM156N`, 1960+; ~Euribor after 1999). Monthly return = previous
month's average rate / 12 (known at the start of the month). Before 1960 the USD T-bill
is used (EUR = USD under the peg then). Interest taxed at 12.5% (proxy for BOT/Bubill).
Sharpe ratios are measured against this EUR cash. The old USD T-bill version is still
reported, as a comparison only.

**Universe** (all converted to EUR, unhedged; monthly; development period ends 2014-12):

| Class | Markets | Source | Start |
|---|---|---|---|
| Equity | US | CRSP via French | 1926 |
| Equity | Germany, France, Italy, Spain, Netherlands, Switzerland, UK, Japan, Canada, Australia | French international country indexes, value-weighted USD total returns | 1975 |
| Govt bonds (10y) | US, Germany, France, Italy, Spain, Netherlands, Switzerland, UK, Japan, Canada, Australia | OECD long-term yields (FRED `IRLTLT01..M156N`), constant-maturity par-bond returns in local currency | 1955–1991 by country |
| FX | local currency per USD | OECD (FRED `CCUSMA02..M618N`), monthly averages | 1957 |

A market enters a strategy only after **12 months** of its data are available at T
(36 months for anything using correlations). No market is ever chosen by looking at its
performance.

**Step B rules (fixed now, monthly rebalancing, long-only, no leverage, rest in EUR cash):**

1. **TSMOM-12**: hold a market if its trailing 12-month return in excess of EUR cash > 0.
2. **SMA-10**: hold a market if its EUR total-return index > its 10-month average.
3. **Risk weighting** of the selected markets: inverse 12-month volatility, then the
   whole portfolio scaled to **10% annual target vol** (trailing 12-month covariance on
   36 months where available, else diagonal), total exposure capped at 100%.
4. **Class budget**: equities and bonds each get half of the risk budget before step 3.

Additional benchmarks for the multi-asset tests:
5. **Global 60/40 buy-and-hold**: 60% equal-weight across available equity markets,
   40% equal-weight across available bond markets, rebalanced monthly.
6. **Global equal-risk buy-and-hold**: rule 3 + 4 applied to all available markets
   without any trend filter (isolates the value of the trend signal).

Main development window for multi-asset results: **1976-01 to 2014-12** (all equity
markets live, 12-month warm-up). Costs: equity 10 bp, bonds 5 bp, cash 0 bp.

## 9. Amendment B: Euribor, currency-hedged equities, scope (2026-10-18)

Decided by Lorenzo on 2026-10-18 ("euro cash + hedge"). Written after the descriptive,
unhedged universe summary of the development period (`results/universe_summary.md`:
per-market CAGR/vol/Sharpe/drawdown, no rule applied) had been produced, and **before**
any hedged return or any step-B rule/benchmark result has been computed.

**Cash leg, precise definition.** EUR cash = German 3-month interbank rate
(`IR3TIB01DEM156N`) from 1960-01 to 1998-12, then the euro-area 3-month rate
(= 3-month Euribor, `IR3TIB01EZM156N`) from 1999-01; if the Euribor value of a month is
not yet available, the German series (which after 1999 is itself Euribor-based) is used.
Before 1960: USD T-bill (peg). Return and tax as in section 8.

**USD T-bill** stays only as a **comparison**: every table that reports it labels it
"USD T-bill (comparison)". All Sharpe ratios, cash allocations and objectives use EUR cash.

**Crypto** is out of the main research: no crypto asset enters the universe, rules,
benchmarks or the holdout test. Any crypto work would be a separate side study with its
own pre-registration, reported apart (its trials still go in `experiments/log.csv`).

**Currency-hedged equity variant (pre-registered test H).**

- Hedged EUR return of equity market c in month t (rolling 1-month forward hedge of the
  start-of-month value, covered interest parity):
  `r_hedged = r_local + (i_EUR - i_c) / 12 - 1 bp`, where `r_local` is the market's
  total return in its own currency, `i_EUR` the EUR cash rate and `i_c` the local
  3-month rate, both of the previous month (known when the hedge is set), and 1 bp per
  month is the roll cost. `r_local` = USD return × change of (local per USD); for the US
  `r_local` is the USD return itself. Euro members after 1998 are already in EUR, so their
  hedged and unhedged returns coincide (carry 0, no cost).
- Local short rate, first available in this order: 3-month interbank (`IR3TIB01{CC}`),
  3-month CD (`IR3TCD01{CC}`), call money (`IRSTCI01{CC}`); US: 3-month T-bill (`TB3MS`).
  A market has a hedged version only from the month it has a local rate.
- Hedge gains/losses are realised monthly and taxed at 26% with loss carry-forward,
  like equity gains.
- **Test:** the global equal-risk benchmark (6), rules 1–3 with the class budget (4), and
  US buy-and-hold are each run twice, equity sleeve unhedged vs hedged, everything else
  identical (bonds stay unhedged). Window **1983-01 to 2014-12** (all hedged markets
  live with a 12-month warm-up), the same for both variants. Statistic: difference in
  Sharpe vs EUR cash (and in max drawdown), paired stationary block bootstrap, mean block
  12 months, 10,000 draws, two-sided 5%. Each run counts as a trial.
- **Decision rule:** the unhedged version stays the default. The hedged version replaces it
  only if its Sharpe is higher with p < 0.05 and it does not breach the 25% drawdown
  limit. Otherwise both are reported and the unhedged version is used.

## 10. Implementation details of step B and test H (2026-10-18)

Fixed when Lorenzo said "go ahead" (2026-10-18), **before** any step-B rule, benchmark 5-6
or test-H result was computed. They resolve points sections 8-9 left open.

- **Eligibility at T:** a market needs its last 12 monthly returns (up to T) all present;
  the correlation matrix uses the last 36 months only if every selected market has them,
  otherwise it is diagonal. Signals of the hedged variant use the hedged returns.
- **Signals:** TSMOM-12 = compounded 12-month return minus compounded 12-month EUR cash
  > 0. SMA-10 = total-return index at T > mean of its last 10 month-end values (T included).
- **Risk weighting + class budget:** within each class, selected markets get weights
  proportional to 1 / (12-month vol), summing to 1; each class portfolio is divided by its
  own estimated vol and given 0.5 (an empty class gives 0); the sum is scaled to 10% annual
  vol with the covariance above; if total exposure > 100% it is scaled down to 100%.
  Rest in EUR cash.
- **Benchmark 5:** 60% equal weight over eligible equity markets, 40% over eligible bond
  markets (eligibility as above), rebalanced monthly to target.
- **Rebalancing:** every month-end to the exact targets (no bands).
- **Taxes:** as in `src/decision/backtest.py`. Income taxed when earned: equity dividend
  yield proxied for every country by the US (Shiller) D/P known at T (no international
  dividend yields in the free data); bond coupon = that country's 10y yield at T / 12,
  12.5%; EUR cash interest 12.5%, all of its return is income. Hedge P&L (hedged minus
  unhedged return) is realised every month at 26%, losses go to the 4-year credit pot.
- **Test H statistic:** Sharpe vs EUR cash of the monthly net returns. Paired stationary
  bootstrap (Politis-Romano, mean block 12, 10,000 draws, seed 0) of the month triples
  (hedged, unhedged, cash); two-sided p = share of |d* - d| >= |d|, d = Sharpe(hedged)
  - Sharpe(unhedged). Same bootstrap gives a 95% interval for the max-drawdown difference.
- **Trials:** each strategy run on each window is one trial in `experiments/log.csv`.

## Changelog

- 2026-10-18: initial version.
- 2026-10-18 (before any results): the equity total-return series is the CRSP
  value-weighted market (French Mkt-RF + RF) as proxy for the S&P 500 TR, because Shiller's
  S&P prices are monthly averages that would flatter trend rules. Shiller data are used for
  valuation features. EUR before 1957 approximated with the Bretton Woods peg (see
  docs/data_lags.md).
- 2026-10-18: Amendment A (section 8): EUR cash leg, international equities and
  government bonds, step-B rules and benchmarks 5-6 fixed before computing any of their
  statistics.
- 2026-10-18: Amendment B (section 9): cash switches to 3-month Euribor from 1999,
  USD T-bill only as labelled comparison, crypto excluded from the main research,
  currency-hedged equity variant and its test fixed before any hedged return or rule
  result was computed (only the descriptive unhedged universe summary existed).
- 2026-10-18: section 10, implementation details of step B and test H fixed before
  running them.
