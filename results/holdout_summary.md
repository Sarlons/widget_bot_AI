# Final holdout test (run once)

Window 2015-01 to 2025-12, never looked at before this run. EUR, after costs
and Italian tax, liquidated at the end. Same code and settings as development.
Frozen protocol: docs/preregistration.md section 13.

| Strategy | Mean log ret | CAGR | Vol | Sharpe (SE) | Sharpe vs USD T-bill (comparison) | Max DD | CVaR 5% (m) | Turnover/yr | Cost+tax drag/yr |
|---|---|---|---|---|---|---|---|---|---|
| TSMOM-12 (final) | 1.21% | 1.21% | 5.8% | 0.13 (0.30) | -0.13 | 14% | -3.5% | 2.74 | 0.77% |
| B6 equal-risk, no filter | 1.39% | 1.40% | 6.0% | 0.15 (0.30) | -0.09 | 17% | -4.1% | 0.44 | 0.59% |
| B5 global 60/40 | 4.28% | 4.37% | 9.0% | 0.45 (0.32) | 0.19 | 16% | -5.7% | 0.12 | 1.35% |
| SMA-10 (step B) | 0.57% | 0.57% | 6.0% | 0.02 (0.30) | -0.19 | 23% | -4.0% | 3.60 | 0.86% |
| US buy-and-hold | 10.57% | 11.15% | 16.5% | 0.69 (0.34) | 0.58 | 20% | -10.9% | 0.00 | 2.03% |

## Pre-registered checks

- max drawdown <= 25%: **pass**
- mean log return above EUR cash (+0.56% per year): **pass**
- Sharpe of the final strategy minus B6: -0.03 (95% bootstrap interval [-0.26, +0.15]); descriptive only, an 11-year window cannot confirm small differences.
