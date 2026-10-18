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

## 11. Amendment C: currencies and gold (2026-10-18)

Lorenzo asked on 2026-10-18 to "finish the rest of the project". Written **before** any
statistic of the assets below has been computed.

**Why no commodity futures.** A futures position earns spot change + roll yield, and the
roll yield (contango/backwardation) needs the futures curve, which no free source gives
over the development period. A modelled roll would be a guess (oil lost tens of percent
to contango in 2005-2014 while spot rose), so oil, copper and broad commodity indexes stay
out. **Gold** needs no roll: a physically backed ETC holds bullion.

**New assets (third class, "alt"):**

| Asset | Return in EUR | Source | Start | Lag |
|---|---|---|---|---|
| `fx_USD`, `fx_GBP`, `fx_JPY`, `fx_CHF`, `fx_CAD`, `fx_AUD`: 3-month deposit in that currency | (1 + i_c of previous month / 12) × change of EUR per unit of c − 1; EUR per c = EUR per USD (as for equities) × USD per c at month-end (FRED daily H.10 `DEXUSUK`, `DEXJPUS`, `DEXSZUS`, `DEXCAUS`, `DEXUSAL`) | FRED | 1971 (rates as in section 9) | 0 |
| `gold`: physically backed ETC | change of USD gold price × change of EUR per USD − 0.25%/12 (fee) | World Bank Pink Sheet, monthly average | 1960 | 1 |

- Gold prices are **monthly averages**, which smooth returns and create artificial
  momentum. To avoid this, gold's trend signals skip the most recent month (months t-12..t-1
  for TSMOM, index at t-1 vs its 10-month average to t-1 for SMA).
- Costs: currencies 5 bp, gold 20 bp per trade. Tax: deposit interest 26% when earned;
  FX and gold gains 26% when realised (capital gains, loss credits as before).

**Test C (pre-registered):** TSMOM-12, SMA-10 and the no-filter equal-risk benchmark (6)
are run with three classes (equity, bond, alt), each with **1/3** of the risk budget,
otherwise exactly as section 10, and compared with their step-B two-class versions on
**1976-01 to 2014-12** (paired stationary bootstrap of the Sharpe difference, as test H).
The three-class version replaces the two-class one only if its Sharpe is higher with
p < 0.05 and its max drawdown is within 25%. An "alt" market needs 12 months of data
like any other.

## 12. Amendment D: crash response, valuation overlay, final selection rule (2026-10-18)

Written while the test-C walk-forward was running and **before** any result of test C,
of the variants below, or of the 2015+ holdout had been seen. The only new fact since
section 11 is the step-B observation that the 12-month trend rules were still invested in
October 1987 (-13% in one month).

**Base:** TSMOM-12 with the classes chosen by test C (two classes unless test C adopted
three), unhedged equities, everything else as section 10.

- **D1, multi-speed trend** (Hurst, Ooi & Pedersen 2017): for each market, the share s of
  three signals that are positive: excess return over EUR cash of the last 1, 3 and 12
  months. A market is held if s > 0, and its inverse-vol weight inside its class is
  multiplied by s (1/3, 2/3 or 1) before the class is scaled.
- **D2, fast volatility:** every volatility used for weights and the 10% target is
  max(3-month, 12-month) realised volatility, so positions shrink as soon as markets get
  turbulent and grow back only slowly. Correlations unchanged.
- **D3:** D1 and D2 together.
- **E, valuation overlay (strategic level):** US CAPE at T = S&P price / average of the
  last 120 months of real earnings (Shiller, with the lags of docs/data_lags.md). If it is
  above the 90th percentile of its own history known at T (from 1881), the equity
  class's risk budget is halved and the freed budget stays in EUR cash. No international
  CAPE is available for free, so the US reading is applied to all equity markets. E is
  applied to the base.

Each is run on 1976-01 to 2014-12 and is one trial. Test as test H/C against the base
(paired bootstrap of the Sharpe difference), reported with max drawdown and CVaR.

**Final selection rule (frozen now).** The candidate set is every strategy run on the
main window 1976-01 to 2014-12 with unhedged equities: TSMOM-12, SMA-10, B5, B6 (step B),
their three-class versions (test C), D1, D2, D3 and E. The final strategy is the one with
the **highest mean log return after costs and tax subject to max drawdown <= 25%**
(section 1 objective). Ties within 0.10 pp per year go to the simpler rule, in the order
B6, TSMOM-12, SMA-10, three-class, D2, D1, D3, E. The rule is applied mechanically; the
candidate list, the chosen strategy and the holdout protocol are then committed in a
"holdout freeze" section before any 2015+ number is computed.

## 13. Holdout freeze (2026-10-18)

Committed **before** any number of the 2015+ holdout has been computed.

**Selection rule applied (section 12)** to the 1976-01..2014-12 candidates (mean log
return after costs and tax, max drawdown): D2 8.15% (16%), TSMOM-12 8.12% (17%),
D3 7.89%, D1 7.80%, SMA-10 7.72%, E 7.67%, TSMOM-12 three classes 7.51%, B5 7.42% (30%,
excluded), SMA-10 three classes 6.78%, B6 6.70%, B6 three classes 5.60%. D2 and TSMOM-12
are within 0.10 pp per year, so the tie goes to the simpler rule:
**final strategy = TSMOM-12, two classes (11 equity + 11 government bond markets, EUR,
unhedged), section 10 settings.** Its development DSR with all 45 logged trials is 0.93.

**Holdout protocol (run once, `src/run_holdout.py`):**
- Window **2015-01 to 2025-12** (last month of the international equity data), first
  decision at 2014-12-31, fresh EUR account, liquidated at the end; same code, costs and
  taxes as development.
- Reported alongside: B6 (equal-risk, no filter), B5 (global 60/40), SMA-10 and US
  buy-and-hold, all two classes, unhedged.
- Checks for the final strategy: (1) max drawdown <= 25%; (2) mean log return above EUR
  cash; (3) Sharpe minus B6 with a paired stationary-bootstrap 95% interval,
  descriptive only (an 11-year window has SE about 0.3 on a Sharpe ratio).
- Whatever the outcome, nothing is re-tuned on the holdout. If check (1) or (2) fails,
  the strategy is not taken to paper trading as is; the result is reported and any new
  idea needs a new pre-registration and new data.
- Paper trading (if the checks pass) follows docs/paper_trading.md, with kill criteria:
  stop if the paper drawdown exceeds 25%; review if it exceeds the 95th percentile of
  the backtest's drawdowns over the same number of months.

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
- 2026-10-18: Amendment C (section 11): currencies and gold as a third class, test C;
  commodity futures excluded (no free roll data). Fixed before computing any of their
  statistics.
- 2026-10-18: Amendment D (section 12): crash-response variants D1-D3, valuation overlay
  E and the final selection rule, fixed before seeing test-C results.
- 2026-10-18: section 13, holdout freeze: final strategy TSMOM-12 (two classes) chosen
  mechanically by the section-12 rule; holdout protocol and checks fixed before running.
- 2026-10-18: bug fix before any holdout number existed: the first holdout run stopped
  with an error because Japan's 10y yield is exactly 0.00% in 2019-01 and 2020-05, where
  the par-bond formula divides by zero. `bond_return` now uses the zero-yield limit. No
  development-period yield is zero, so no development result changes. No metric was
  computed in the failed run; the holdout is then run (once) with the fixed code.
