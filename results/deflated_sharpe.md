# Deflated Sharpe Ratio (development period)

Probability that the true Sharpe (vs EUR cash, after costs and tax) is above zero,
after correcting for the number of strategies tried, the spread of their Sharpe
ratios and non-normal returns (Bailey & Lopez de Prado 2014). DSR > 0.95 = survives.

- Trials in `experiments/log.csv`: **45** (37 distinct configurations;
  re-runs of the same benchmark at later commits counted separately in the first number).
- Std of annualised Sharpe across the 35 distinct strategy trials: 0.120.
- Sharpe that the best of N skill-less trials would reach by luck (annualised): **0.27** with N = 45, 0.26 with N = 37.

| Strategy | Window | Sharpe | Skew | Kurtosis | PSR (vs 0) | DSR, N all | DSR, N distinct |
|---|---|---|---|---|---|---|---|
| tsmom12 (unhedged) | 1976-01..2014-12 | 0.54 | -1.39 | 10.2 | 0.999 | 0.932 | 0.938 |
| sma10 (unhedged) | 1976-01..2014-12 | 0.52 | -1.54 | 11.2 | 0.998 | 0.920 | 0.927 |
| eq_risk (unhedged) | 1976-01..2014-12 | 0.39 | -0.51 | 4.2 | 0.991 | 0.768 | 0.785 |
| global_60_40 (unhedged) | 1976-01..2014-12 | 0.33 | -0.68 | 4.4 | 0.978 | 0.656 | 0.676 |
| eq_risk (unhedged) | 1983-01..2014-12 | 0.55 | -0.41 | 3.8 | 0.999 | 0.937 | 0.943 |
| eq_risk (hedged) | 1983-01..2014-12 | 0.55 | -0.53 | 4.1 | 0.999 | 0.938 | 0.944 |
| tsmom12 (unhedged) | 1983-01..2014-12 | 0.60 | -1.44 | 11.0 | 0.998 | 0.950 | 0.954 |
| tsmom12 (hedged) | 1983-01..2014-12 | 0.57 | -1.67 | 12.9 | 0.997 | 0.926 | 0.932 |
| sma10 (unhedged) | 1983-01..2014-12 | 0.68 | -1.46 | 12.4 | 0.999 | 0.976 | 0.979 |
| sma10 (hedged) | 1983-01..2014-12 | 0.60 | -1.87 | 15.3 | 0.998 | 0.940 | 0.945 |
| us_buy_hold (unhedged) | 1983-01..2014-12 | 0.33 | -0.81 | 4.7 | 0.962 | 0.629 | 0.647 |
| us_buy_hold (hedged) | 1983-01..2014-12 | 0.39 | -1.01 | 6.0 | 0.981 | 0.744 | 0.760 |

Caveats: the trials are strongly correlated (same markets, overlapping windows), so
N overstates the number of independent tries and the DSR is conservative. The
variance of trial Sharpes mixes different windows. Holdout 2015+ untouched.
