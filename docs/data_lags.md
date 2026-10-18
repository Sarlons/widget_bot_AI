# Data sources and publication lags

`availability_date = month-end of observation month + lag (months)`.
A record is visible to a forecast made at date T only if `availability_date <= T`.
Lags are deliberately conservative. They are encoded in `src/ingest/*.py`.

| Series (store name) | Source | Frequency / start | Lag | Reason |
|---|---|---|---|---|
| `shiller_P` S&P Composite price | Shiller | monthly avg of daily closes, 1871 | 0 | known at month end |
| `shiller_rate` long rate (GS10) | Shiller | monthly avg, 1871 | 0 | known at month end |
| `shiller_CPI` | Shiller | 1871 | 1 (15 before 1913) | CPI released mid next month; pre-1913 annual index interpolated |
| `shiller_D` dividends | Shiller | 1871 | 6 (15 before 1926) | quarterly S&P data interpolated, reported ~3m after quarter; pre-1926 annual Cowles data interpolated |
| `shiller_E` earnings | Shiller | 1871 | 6 (15 before 1926) | as dividends |
| `fred_TB3MS` 3m T-bill | FRED | monthly avg, 1934 | 0 | market rate |
| `fred_GS10` 10y Treasury | FRED | monthly avg, 1953 | 0 | market rate |
| `fred_CPIAUCSL` CPI | FRED | 1947 | 1 | released ~mid next month |
| `fred_UNRATE` unemployment | FRED | 1948 | 1 | released 1st Friday of next month |
| `fred_BAA`, `fred_AAA` corporate yields | FRED (Moody's) | monthly avg, 1919 | 0 | market rates |
| `fred_DEXUSEU` USD per EUR | FRED | daily -> month-end, 1999 | 0 | market rate; only completed months stored |
| `fred_CCUSMA02DEM618N` EUR per USD (DEM-based) | FRED (OECD) | monthly avg, 1957 | 0 | market rate (OECD compiles later, rates were public) |
| `ff_MKT_RF`, `ff_SMB`, `ff_HML`, `ff_RF` | Kenneth French | monthly, 1926-07 | 0 | computed from month-end prices |

## Known limitations

- **Revisions not captured.** FRED/Shiller give today's revised values (CPI, unemployment,
  earnings). Lags are respected, revisions are not. ALFRED vintages could fix this later.
- **Shiller prices are monthly averages**, which create spurious autocorrelation. For
  returns and trend rules we use CRSP month-end total returns (French) instead.
- **Shiller file currently ends 2024-09** (shillerdata.com). Equity returns come from
  French (to 2026-08), so this only limits valuation features near the present.
- **EUR before 1957** is approximated by the Bretton Woods peg (EUR returns = USD returns).
- The store is append-only: a re-download with revised values adds a new vintage;
  `as_of` uses the most recently downloaded value among those already available at T.
