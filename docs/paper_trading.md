# Paper trading

Research and education only. No broker, no real money, nothing is sent anywhere.

**Strategy:** TSMOM-12 with two classes (11 equity + 11 government bond markets, EUR,
unhedged), exactly as frozen in `docs/preregistration.md` section 13.

## Monthly routine (a few days after each month-end)

```
.venv\Scripts\python -m src.ingest.run_all
.venv\Scripts\python -m src.paper.run_paper
```

The run books last month's paper return from last month's weights, prints next month's
target weights and appends both to `paper/decisions.csv` and `paper/track.csv`.
Commit those two files after each run so the track record carries dates.

## Live inputs (differ from the research data)

| Input | Research | Live |
|---|---|---|
| Country equities | French international indexes (updated yearly) | US-listed iShares MSCI country ETFs, SPY for the US (Yahoo, dividend-adjusted, unofficial) |
| 10y yields, short rates, FX | FRED/OECD | same, but published 1-2 months late: a missing month is carried forward from the last value (at most 2 months, flagged in `notes`) |
| EUR cash | German 3m / Euribor | same (German series while FRED's Euribor series lags) |

## Data-quality stops (nothing is booked)

- a market or cash has no value for the decision month;
- a monthly return above 30% in absolute value;
- an input more than 2 months stale.

## Kill criteria (pre-registered, section 13)

- **Stop** if the paper drawdown exceeds 25% (the objective's limit).
- **Review** if the paper drawdown exceeds the 95th percentile of the development
  backtest's drawdowns over the same number of months (`paper/backtest_drawdown_quantiles.csv`:
  about 9% after 6 months, 13% after 12, 17% after 60).

## What paper trading can and cannot show

A year or two of results cannot confirm an edge: the Sharpe ratio's standard error over
two years is about 0.7. It can confirm that the pipeline runs without leakage and that live
results stay inside the backtest's range. The tracked return is after trading costs and
before tax (the backtest's tax drag was about 1-2% a year).
