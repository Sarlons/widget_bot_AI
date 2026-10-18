# Step D: crash response and valuation overlay (development period)

Window 1976-01 to 2014-12, classes eq, bond. EUR, after costs
and Italian tax, liquidated at the end. Sharpe vs EUR cash. Holdout 2015+ untouched.
E halved the equity budget in 34% of the months (US CAPE above the 90th
percentile of its point-in-time history).

| Variant | Mean log ret | CAGR | Vol | Sharpe (SE) | Sharpe vs USD T-bill (comparison) | Max DD | CVaR 5% (m) | Oct 1987 | Turnover/yr | Cost+tax drag/yr |
|---|---|---|---|---|---|---|---|---|---|---|
| TSMOM-12 (base) | 8.12% | 8.46% | 7.0% | 0.54 (0.17) | 0.43 | 17% | -4.4% | -13.3% | 2.09 | 1.86% |
| D1 multi-speed trend | 7.80% | 8.12% | 6.3% | 0.54 (0.17) | 0.41 | 19% | -3.7% | -11.5% | 2.84 | 1.92% |
| D2 fast volatility | 8.15% | 8.49% | 6.9% | 0.55 (0.17) | 0.44 | 16% | -4.3% | -12.2% | 2.30 | 1.90% |
| D3 = D1 + D2 | 7.89% | 8.21% | 6.2% | 0.56 (0.17) | 0.42 | 18% | -3.7% | -10.8% | 2.96 | 1.95% |
| E valuation overlay | 7.67% | 7.97% | 6.7% | 0.49 (0.17) | 0.39 | 17% | -4.3% | -13.3% | 2.05 | 1.69% |

## Variant minus base

Paired stationary bootstrap (mean block 12, 10,000 draws).

| Variant | Sharpe diff | 95% CI | p | Max DD diff | 95% CI |
|---|---|---|---|---|---|
| D1 multi-speed trend | +0.00 | [-0.13, +0.12] | 0.940 | +2% | [-7%, +3%] |
| D2 fast volatility | +0.01 | [-0.02, +0.05] | 0.515 | -0% | [-3%, +1%] |
| D3 = D1 + D2 | +0.02 | [-0.12, +0.15] | 0.721 | +2% | [-7%, +2%] |
| E valuation overlay | -0.04 | [-0.10, +0.01] | 0.102 | +0% | [-3%, +1%] |

All variants stay candidates for the final selection rule (section 12).
