# Step B: multi-asset rules and currency-hedge test (development period)

EUR, after costs and Italian tax, liquidated at the end of each window. Monthly
rebalancing, long-only, rest in EUR cash. Sharpe is the excess over EUR cash; its
SE ≈ sqrt((1+SR²/2)/years). `Sharpe vs USD T-bill (comparison)` is for reference only.
Holdout 2015+ untouched. Rules fixed in docs/preregistration.md sections 8-10.

## Step B: 1976-01..2014-12

| Rule | Equity | Mean log ret | CAGR | Vol | Sharpe (SE) | Sharpe vs USD T-bill (comparison) | Max DD | CVaR 5% (m) | Turnover/yr | Cost+tax drag/yr |
|---|---|---|---|---|---|---|---|---|---|---|
| TSMOM-12 | unhedged | 8.12% | 8.46% | 7.0% | 0.54 (0.17) | 0.43 | 17% | -4.4% | 2.09 | 1.86% |
| SMA-10 | unhedged | 7.72% | 8.03% | 6.3% | 0.52 (0.17) | 0.39 | 20% | -3.9% | 2.03 | 1.77% |
| Equal-risk, no filter (B6) | unhedged | 6.70% | 6.93% | 5.8% | 0.39 (0.17) | 0.30 | 15% | -3.3% | 0.43 | 1.39% |
| Global 60/40 (B5) | unhedged | 7.42% | 7.70% | 9.9% | 0.33 (0.16) | 0.33 | 30% ⚠ | -6.3% | 0.18 | 1.65% |

## Test H runs: 1983-01..2014-12

| Rule | Equity | Mean log ret | CAGR | Vol | Sharpe (SE) | Sharpe vs USD T-bill (comparison) | Max DD | CVaR 5% (m) | Turnover/yr | Cost+tax drag/yr |
|---|---|---|---|---|---|---|---|---|---|---|
| Equal-risk, no filter (B6) | unhedged | 7.02% | 7.27% | 5.6% | 0.55 (0.19) | 0.42 | 15% | -3.0% | 0.41 | 1.41% |
| Equal-risk, no filter (B6) | hedged | 6.94% | 7.19% | 5.4% | 0.55 (0.19) | 0.38 | 13% | -3.0% | 0.41 | 1.40% |
| TSMOM-12 | unhedged | 7.83% | 8.14% | 6.6% | 0.60 (0.19) | 0.49 | 17% | -4.0% | 2.06 | 1.77% |
| TSMOM-12 | hedged | 7.50% | 7.79% | 6.4% | 0.57 (0.19) | 0.43 | 17% | -4.0% | 2.12 | 1.71% |
| SMA-10 | unhedged | 8.02% | 8.35% | 6.1% | 0.68 (0.20) | 0.52 | 20% | -3.4% | 1.92 | 1.79% |
| SMA-10 | hedged | 7.46% | 7.74% | 6.0% | 0.60 (0.19) | 0.43 | 19% | -3.7% | 1.99 | 1.67% |
| US buy-and-hold | unhedged | 8.20% | 8.55% | 17.2% | 0.33 (0.18) | 0.42 | 60% ⚠ | -11.5% | 0.00 | 1.29% |
| US buy-and-hold | hedged | 8.92% | 9.33% | 15.6% | 0.39 (0.18) | 0.36 | 50% ⚠ | -10.7% | 0.00 | 1.78% |

⚠ = breaches the 25% drawdown limit (rejected under the pre-registered objective).

## Test H: hedged minus unhedged (1983-01..2014-12)

Paired stationary bootstrap, mean block 12 months, 10,000 draws.
Decision rule: hedged replaces unhedged only if its Sharpe is higher with
p < 0.05 and its max drawdown is within 25%.

| Strategy | Sharpe diff | 95% CI | p | Max DD diff | 95% CI | Hedged adopted? |
|---|---|---|---|---|---|---|
| Equal-risk, no filter (B6) | +0.00 | [-0.04, +0.06] | 0.862 | -2% | [-3%, +1%] | no |
| TSMOM-12 | -0.04 | [-0.12, +0.06] | 0.453 | +1% | [-4%, +4%] | no |
| SMA-10 | -0.09 | [-0.15, -0.01] | 0.017 | -1% | [-2%, +2%] | no |
| US buy-and-hold | +0.06 | [-0.17, +0.31] | 0.615 | -10% | [-23%, +9%] | no |

Limits: bond returns are modelled from monthly-average yields; FX for bonds and
for the hedged local returns uses OECD monthly averages; foreign dividend tax uses
the US dividend yield as proxy; US withholding and foreign withholding ignored.
