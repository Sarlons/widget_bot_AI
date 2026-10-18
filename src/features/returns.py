"""Monthly total-return panel built ONLY from data known at date T.

    panel = returns_panel(records, T)

Columns (monthly, simple returns, decimals):
  eq_usd   US equity total return in USD  (CRSP market = ff_MKT_RF + ff_RF; S&P 500 proxy)
  rf_usd   1-month T-bill return in USD   (ff_RF)
  bond_usd 10-year Treasury total return  (constant-maturity par bond, priced from yields)
  fx       EUR per 1 USD, month-end (1999+) or monthly average (earlier, see below)
  eq, rf, bond   the same returns converted to EUR (unhedged): (1+r_usd)*(fx_t/fx_t-1) - 1
  eq_index       cumulated equity total-return index in USD (for trend rules)

EUR before 1999: Germany's DEM rate converted at the official 1.95583 DEM/EUR (OECD series,
1957+). Before 1957 the rate is held at the Bretton Woods peg 4.20 DEM/USD, i.e. EUR
returns equal USD returns. This is an approximation: treat pre-1957 EUR results as USD.

Note: the EUR return of a T-bill is NOT risk-free for a euro investor (it includes FX).
"""
from __future__ import annotations

import pandas as pd

from src.ingest.store import as_of

DEM_PER_EUR = 1.95583
PEG_EUR_PER_USD = 4.20 / DEM_PER_EUR

SERIES = ["ff_MKT_RF", "ff_RF", "shiller_rate", "fred_GS10", "fred_DEXUSEU",
          "fred_CCUSMA02DEM618N"]


def bond_return(yields: pd.Series, maturity: float = 10.0) -> pd.Series:
    """Monthly total return of a constant-maturity par bond, from annual yields.

    Buy at t-1 a `maturity`-year bond paying coupon y(t-1) semi-annually (price 1);
    one month later it has maturity - 1/12 years left and is priced at yield y(t).
    Return = accrued coupon + price change. (Yields are monthly averages, so returns
    are slightly smoothed.)
    """
    c = yields.shift(1)
    y = yields
    n = 2 * (maturity - 1 / 12)
    price = c / y * (1 - (1 + y / 2) ** (-n)) + (1 + y / 2) ** (-n)
    return price - 1 + c / 12


def returns_panel(records: pd.DataFrame, T) -> pd.DataFrame:
    d = as_of(records, T, SERIES)
    p = pd.DataFrame(index=d.index)
    p["eq_usd"] = d["ff_MKT_RF"] + d["ff_RF"]
    p["rf_usd"] = d["ff_RF"]
    long_rate = d["fred_GS10"].combine_first(d["shiller_rate"])
    p["bond_usd"] = bond_return(long_rate)

    fx = (1.0 / d["fred_DEXUSEU"]).combine_first(d["fred_CCUSMA02DEM618N"])
    fx[fx.index < pd.Timestamp("1957-01-01")] = PEG_EUR_PER_USD
    p["fx"] = fx.ffill()
    fx_ret = p["fx"] / p["fx"].shift(1)
    for col in ("eq", "rf", "bond"):
        p[col] = (1 + p[f"{col}_usd"]) * fx_ret - 1
    p["eq_index"] = (1 + p["eq_usd"].fillna(0)).cumprod().where(p["eq_usd"].notna())
    return p.dropna(subset=["eq_usd"])
