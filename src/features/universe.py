"""Multi-asset universe (pre-registration amendment A): monthly EUR returns known at T.

    u = universe_panel(records, T)

Columns (simple monthly returns in EUR, unhedged; NaN before a market's data start):
  eq_US, eq_DE, eq_FR, ...    equity total returns
  bond_US, bond_DE, ...       10-year government bond total returns (par-bond model)
  cash                        EUR cash (German 3-month rate)

Conversions:
  * Equities: French country returns are in USD -> EUR with the same EUR/USD series used
    for the US (returns.py).
  * Bonds: return in local currency from the OECD 10y yield, then local -> EUR with the
    OECD cross rate (EUR per USD) / (local per USD). Both are monthly averages, so FX
    moves are slightly smoothed. Euro members use rate 1 from 1999 (same currency).
"""
from __future__ import annotations

import pandas as pd

from src.features.returns import SERIES as BASE_SERIES
from src.features.returns import bond_return, returns_panel
from src.ingest.store import as_of

EQUITY = ["US", "DE", "FR", "IT", "ES", "NL", "CH", "GB", "JP", "CA", "AU"]
BONDS = ["US", "DE", "FR", "IT", "ES", "NL", "CH", "GB", "JP", "CA", "AU"]
EURO_MEMBERS = {"DE", "FR", "IT", "ES", "NL"}
EURO_START = pd.Timestamp("1999-01-31")

SERIES = sorted(set(
    BASE_SERIES
    + [f"ffi_{c}" for c in EQUITY if c != "US"]
    + [f"fred_IRLTLT01{c}M156N" for c in BONDS if c != "US"]
    + [f"fred_CCUSMA02{c}M618N" for c in BONDS if c != "US"]
))


def universe_panel(records: pd.DataFrame, T) -> pd.DataFrame:
    d = as_of(records, T, SERIES)
    base = returns_panel(records, T)
    u = pd.DataFrame(index=base.index)
    fx_ret = base["fx"] / base["fx"].shift(1)  # EUR per USD, change

    u["eq_US"] = base["eq"]
    for c in EQUITY[1:]:
        u[f"eq_{c}"] = (1 + d[f"ffi_{c}"].reindex(u.index)) * fx_ret - 1

    u["bond_US"] = base["bond"]
    eur_per_usd_avg = d["fred_CCUSMA02DEM618N"]
    for c in BONDS[1:]:
        local = bond_return(d[f"fred_IRLTLT01{c}M156N"])
        eur_per_local = eur_per_usd_avg / d[f"fred_CCUSMA02{c}M618N"]
        if c in EURO_MEMBERS:
            eur_per_local[eur_per_local.index >= EURO_START] = 1.0
        fx_local = eur_per_local / eur_per_local.shift(1)
        u[f"bond_{c}"] = ((1 + local) * fx_local - 1).reindex(u.index)

    u["cash"] = base["cash"]
    return u
