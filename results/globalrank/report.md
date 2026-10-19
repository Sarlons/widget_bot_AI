# Global index ranking: automated analysis

Generated 2026-10-19. Research and education only, not financial advice. EUR, after ETF costs and Italian tax. Full report with charts: report.html.

## Summary

- No AI model passed the development checks: none beat both the simple momentum rank and world buy-and-hold after costs and tax with a deflated Sharpe of at least 0.95. The 2022-2025 test was run for all models for information.
- Development 1995-2021: world buy-and-hold made 7.5% a year (log), worst fall 53%; momentum M0 made 6.1%, worst fall 56%; the best AI model (M1 linear ranking model) made 5.8%, worst fall 55%.
- Test 2022-2025: world buy-and-hold made 6.1% a year; the best ranking strategy (M0 momentum 12-1 (no model)) made 3.9%.
- 6 variants were run in development and are all logged; with that many, luck alone would give the best one a Sharpe of about 0.16.

## Development 1995-2021

| Strategy | Mean log return/yr | CAGR | Volatility | Sharpe (SE) | Max drawdown | CVaR 5% (month) | Turnover/yr | Cost+tax drag/yr | Sharpe minus World [95%] | Deflated Sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| World buy-and-hold (benchmark) | 7.55% | 7.8% | 14.9% | 0.45 (0.20) | 53% | -10.4% | 0.00 | 0.90% |  | 0.92 |
| US buy-and-hold | 9.69% | 10.2% | 16.5% | 0.56 (0.21) | 59% | -10.9% | 0.00 | 0.94% | +0.10 [-0.05, +0.23] | 0.97 |
| Equal weight, all indexes | 7.01% | 7.3% | 15.3% | 0.41 (0.20) | 55% | -10.7% | 0.15 | 1.67% | -0.04 [-0.23, +0.13] | 0.89 |
| M0 momentum 12-1 (no model) | 6.10% | 6.3% | 15.1% | 0.36 (0.20) | 56% | -10.1% | 1.61 | 3.83% | -0.10 [-0.34, +0.12] | 0.83 |
| M1 linear ranking model | 5.82% | 6.0% | 14.7% | 0.34 (0.20) | 55% | -10.2% | 1.95 | 4.22% | -0.11 [-0.35, +0.11] | 0.81 |
| M2 gradient-boosted trees | 3.52% | 3.6% | 15.0% | 0.18 (0.19) | 59% | -10.4% | 3.41 | 5.19% | -0.27 [-0.50, -0.08] | 0.55 |

## Development checks

| Model | beats M0 | beats W | drawdown <= W | DSR >= 0.95 |
|---|---|---|---|---|
| M1 linear ranking model | no | no | no | no |
| M2 gradient-boosted trees | no | no | no | no |

## Test 2022-2025 (run once)

| Strategy | Mean log return/yr | CAGR | Volatility | Sharpe (SE) | Max drawdown | CVaR 5% (month) | Turnover/yr | Cost+tax drag/yr | Sharpe minus World [95%] |
|---|---|---|---|---|---|---|---|---|---|
| World buy-and-hold (benchmark) | 6.10% | 6.3% | 14.2% | 0.34 (0.51) | 12% | -7.4% | 0.00 | 1.82% |  |
| US buy-and-hold | 6.72% | 7.0% | 16.6% | 0.35 (0.52) | 16% | -9.3% | 0.00 | 1.95% | +0.01 [-0.11, +0.15] |
| Equal weight, all indexes | 4.75% | 4.9% | 11.7% | 0.27 (0.51) | 13% | -6.5% | 0.13 | 1.77% | -0.07 [-0.51, +0.31] |
| M0 momentum 12-1 (no model) | 3.87% | 3.9% | 12.2% | 0.19 (0.50) | 13% | -6.9% | 1.85 | 3.22% | -0.15 [-0.65, +0.25] |
| M1 linear ranking model | 3.15% | 3.2% | 12.0% | 0.13 (0.50) | 16% | -7.0% | 2.10 | 3.54% | -0.21 [-0.71, +0.22] |
| M2 gradient-boosted trees | 2.71% | 2.7% | 11.6% | 0.09 (0.50) | 15% | -6.7% | 2.21 | 3.75% | -0.25 [-0.72, +0.20] |
