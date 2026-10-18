# Step C: currencies and gold as a third class (development period)

Window 1976-01 to 2014-12. EUR, after costs and Italian tax, liquidated at
the end. Sharpe vs EUR cash; `vs USD T-bill (comparison)` for reference only.
Alt = 3-month deposits in USD, GBP, JPY, CHF, CAD, AUD and a gold ETC.
Holdout 2015+ untouched. Rules: docs/preregistration.md sections 10-11.

| Rule | Classes | Mean log ret | CAGR | Vol | Sharpe (SE) | Sharpe vs USD T-bill (comparison) | Max DD | CVaR 5% (m) | Avg alt weight | Turnover/yr | Cost+tax drag/yr |
|---|---|---|---|---|---|---|---|---|---|---|---|
| TSMOM-12 | 2 classes | 8.12% | 8.46% | 7.0% | 0.54 (0.17) | 0.43 | 17% | -4.4% | 0% | 2.09 | 1.86% |
| TSMOM-12 | 3 classes | 7.51% | 7.80% | 6.8% | 0.47 (0.17) | 0.41 | 14% | -3.7% | 32% | 2.36 | 2.10% |
| SMA-10 | 2 classes | 7.72% | 8.03% | 6.3% | 0.52 (0.17) | 0.39 | 20% | -3.9% | 0% | 2.03 | 1.77% |
| SMA-10 | 3 classes | 6.78% | 7.02% | 5.8% | 0.41 (0.17) | 0.35 | 16% | -3.2% | 34% | 2.29 | 1.90% |
| Equal-risk, no filter (B6) | 2 classes | 6.70% | 6.93% | 5.8% | 0.39 (0.17) | 0.30 | 15% | -3.3% | 0% | 0.43 | 1.39% |
| Equal-risk, no filter (B6) | 3 classes | 5.60% | 5.76% | 5.4% | 0.21 (0.16) | 0.22 | 14% | -2.9% | 36% | 0.46 | 1.40% |

## Test C: 3 classes minus 2 classes

Paired stationary bootstrap (mean block 12, 10,000 draws). The 3-class version
is adopted only if its Sharpe is higher with p < 0.05 and max DD <= 25%.

| Rule | Sharpe diff | 95% CI | p | Max DD diff | 95% CI | Adopted? |
|---|---|---|---|---|---|---|
| TSMOM-12 | -0.07 | [-0.25, +0.07] | 0.372 | -3% | [-8%, -0%] | no |
| SMA-10 | -0.11 | [-0.30, +0.06] | 0.225 | -5% | [-9%, -0%] | no |
| Equal-risk, no filter (B6) | -0.18 | [-0.34, -0.02] | 0.028 | -1% | [-6%, +2%] | no |

Limits: gold uses monthly-average prices (signals skip the last month); EUR per
USD before 1999 is an OECD monthly average for every EUR conversion; Italian tax on
currency gains simplified to 26% on realised gains.
