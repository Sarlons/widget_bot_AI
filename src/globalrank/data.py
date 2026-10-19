"""Project 2 universe: monthly EUR total returns of country indexes known at T.

    p = panel_at(records, T)

Columns: one per index (`AT`, `BE`, ..., `US`, `EM`), the benchmark `WORLD` (developed
markets, MSCI World proxy) and `cash` (EUR cash, as project 1). Returns are in EUR,
unhedged, net of the ETF running cost (TER) of section 6 of
docs/globalrank_preregistration.md. NaN before an index's data start.
"""
from __future__ import annotations

import pandas as pd

from src.features.returns import SERIES as BASE_SERIES
from src.features.returns import returns_panel
from src.ingest.store import as_of

EUROPE = ["AT", "BE", "DK", "FI", "FR", "DE", "IE", "IT", "NL", "NO", "ES", "SE", "CH", "GB"]
OTHER = ["US", "JP", "CA", "AU", "HK", "SG", "NZ", "MY"]
ASSETS = EUROPE + OTHER + ["EM"]
NAMES = {"AT": "Austria", "BE": "Belgium", "DK": "Denmark", "FI": "Finland", "FR": "France",
         "DE": "Germany", "IE": "Ireland", "IT": "Italy", "NL": "Netherlands", "NO": "Norway",
         "ES": "Spain", "SE": "Sweden", "CH": "Switzerland", "GB": "UK", "US": "USA",
         "JP": "Japan", "CA": "Canada", "AU": "Australia", "HK": "Hong Kong",
         "SG": "Singapore", "NZ": "New Zealand", "MY": "Malaysia", "EM": "Emerging markets",
         "WORLD": "World (developed, MSCI World proxy)"}
TER_INDEX = 0.0030 / 12  # per month, country and EM ETFs
TER_WORLD = 0.0020 / 12
SERIES = sorted(set(BASE_SERIES + [f"ffi_{c}" for c in ASSETS if c not in ("US", "EM")]
                    + ["frg_DEV", "frg_EM"]))


def panel_at(records: pd.DataFrame, T) -> pd.DataFrame:
    d = as_of(records, T, SERIES)
    base = returns_panel(records, T)
    p = pd.DataFrame(index=base.index)
    fx_ret = base["fx"] / base["fx"].shift(1)

    def eur(usd: pd.Series) -> pd.Series:
        return (1 + usd.reindex(p.index)) * fx_ret - 1

    for c in ASSETS:
        if c == "US":
            p[c] = base["eq"]
        elif c == "EM":
            p[c] = eur(d["frg_EM"])
        else:
            p[c] = eur(d[f"ffi_{c}"])
        p[c] -= TER_INDEX
    p["WORLD"] = eur(d["frg_DEV"]) - TER_WORLD
    p["cash"] = base["cash"]
    return p
