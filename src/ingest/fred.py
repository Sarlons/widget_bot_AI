"""FRED (Federal Reserve Bank of St. Louis) series, via the free CSV endpoint (no API key).

Series and publication lags (months after the observation month ends):
  TB3MS     3-month T-bill rate, monthly average           lag 0   (1934+)
  GS10      10-year Treasury yield, monthly average        lag 0   (1953+)
  CPIAUCSL  CPI, all urban consumers, seasonally adjusted  lag 1   (1947+) released mid next month
  UNRATE    Unemployment rate                              lag 1   (1948+) released 1st Friday next month
  BAA, AAA  Moody's corporate bond yields, monthly average lag 0   (1919+) credit spread = BAA - AAA
  DEXUSEU   USD per EUR, daily -> month-end value          lag 0   (1999+)
  CCUSMA02DEM618N  OECD: EUR per USD for Germany (DEM converted at the fixed 1.95583),
                   monthly average                         lag 0   (1957+), EUR proxy before 1999

Multi-asset universe (amendment A, all lag 0: market rates, monthly averages):
  IR3TIB01DEM156N    German 3-month interbank rate (EUR cash)            (1960+)
  IR3TIB01EZM156N    euro-area 3-month interbank rate = 3m Euribor       (1994+, used 1999+)

Local short rates for the currency-hedged equity variant (amendment B, lag 0):
  IR3TIB01{CC}M156N  3-month interbank rate, country CC
  IR3TCD01JPM156N    Japan 3-month CD rate (1979+, before the interbank series starts 2002)
  IRSTCI01{CC}M156N  call money rate, Japan (1985+) and Switzerland (1972+) as last fallback

Currency deposits (amendment C), daily H.10 noon rates -> month-end, lag 0 (1971+):
  DEXUSUK USD per GBP, DEXUSAL USD per AUD, DEXJPUS JPY per USD, DEXSZUS CHF per USD,
  DEXCAUS CAD per USD
  IRLTLT01{CC}M156N  OECD 10-year government bond yield, country CC
  CCUSMA02{CC}M618N  OECD national currency per USD (euro members in EUR units)

Rates are stored as decimals (5.0% -> 0.05). CPI/UNRATE values are today's revised
numbers (revisions not captured; see store.py).

Run:  .venv\\Scripts\\python -m src.ingest.fred
"""
from __future__ import annotations

import io

import pandas as pd

from src.ingest.download import fetch
from src.ingest.store import add_months, append_records, month_end, now_utc, save_raw

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"

# series id -> (lag in months, is a percentage rate, is daily)
SERIES = {
    "TB3MS": (0, True, False),
    "GS10": (0, True, False),
    "CPIAUCSL": (1, False, False),
    "UNRATE": (1, True, False),
    "BAA": (0, True, False),
    "AAA": (0, True, False),
    "DEXUSEU": (0, False, True),
    "CCUSMA02DEM618N": (0, False, False),
    "IR3TIB01DEM156N": (0, True, False),
}
BOND_COUNTRIES = ["DE", "FR", "IT", "ES", "NL", "CH", "GB", "JP", "CA", "AU"]
FX_COUNTRIES = ["FR", "IT", "ES", "NL", "CH", "GB", "JP", "CA", "AU"]  # DE already above
SERIES.update({f"IRLTLT01{cc}M156N": (0, True, False) for cc in BOND_COUNTRIES})
SERIES.update({f"CCUSMA02{cc}M618N": (0, False, False) for cc in FX_COUNTRIES})
SERIES["IR3TIB01EZM156N"] = (0, True, False)
SERIES.update({f"IR3TIB01{cc}M156N": (0, True, False) for cc in FX_COUNTRIES})
SERIES.update({sid: (0, True, False) for sid in
               ("IR3TCD01JPM156N", "IRSTCI01JPM156N", "IRSTCI01CHM156N")})
SERIES.update({sid: (0, False, True) for sid in
               ("DEXUSUK", "DEXUSAL", "DEXJPUS", "DEXSZUS", "DEXCAUS")})


def parse(sid: str, content: bytes) -> pd.DataFrame:
    lag, is_pct, is_daily = SERIES[sid]
    df = pd.read_csv(io.BytesIO(content))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")  # FRED uses "." for missing
    df = df.dropna()
    if is_daily:
        # month-end value = last available daily observation of each COMPLETED month
        df = df[df["date"].dt.to_period("M") < pd.Timestamp.today().to_period("M")]
        df = df.groupby(df["date"].dt.to_period("M")).last()
    obs = month_end(df["date"])
    value = df["value"].to_numpy(dtype=float)
    if is_pct:
        value = value / 100.0
    return pd.DataFrame({
        "series": f"fred_{sid}",
        "observation_date": obs,
        "availability_date": add_months(obs, lag),
        "value": value,
    })


def ingest() -> int:
    ts = now_utc()
    added = 0
    for sid in SERIES:
        content = fetch(URL.format(sid=sid))
        save_raw("fred", f"{sid}.csv", content, ts)
        added += append_records("fred", parse(sid, content), ts)
    return added


if __name__ == "__main__":
    print(f"fred: {ingest()} new records")
