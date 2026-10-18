"""Multi-asset universe (pre-registration amendment A): monthly EUR returns known at T.

    u = universe_panel(records, T)

Columns (simple monthly returns in EUR, unhedged; NaN before a market's data start):
  eq_US, eq_DE, eq_FR, ...    equity total returns
  bond_US, bond_DE, ...       10-year government bond total returns (par-bond model)
  eqh_US, eqh_DE, ...         currency-HEDGED equity returns (amendment B, test H)
  cash                        EUR cash (German 3m rate to 1998, 3m Euribor from 1999)

Conversions:
  * Equities: French country returns are in USD -> EUR with the same EUR/USD series used
    for the US (returns.py).
  * Hedged equity (rolling 1-month forward, covered interest parity):
      r_hedged = r_local + (i_EUR - i_local) / 12 - 1 bp
    with both rates of the previous month (known when the hedge is set). r_local =
    USD return x change of (local per USD, OECD monthly average). Euro members from 1999
    are already in EUR: hedged = unhedged, no cost. Local rate chain: 3m interbank ->
    3m CD -> call money; US: 3m T-bill. No hedged value before a local rate exists.
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

HEDGE_COST = 0.0001  # per month
LOCAL_RATE_CHAIN = ["fred_IR3TIB01{c}M156N", "fred_IR3TCD01{c}M156N", "fred_IRSTCI01{c}M156N"]

SERIES = sorted(set(
    BASE_SERIES
    + ["fred_TB3MS"]
    + [t.format(c=c) for c in EQUITY if c != "US" for t in LOCAL_RATE_CHAIN]
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

    # ---- currency-hedged equities (amendment B) ----
    i_eur = base["cash_rate"].shift(1)
    for c in EQUITY:
        if c == "US":
            r_local = base["eq_usd"]
            i_local = d["fred_TB3MS"]
        else:
            local_per_usd = d[f"fred_CCUSMA02{c}M618N"]
            r_local = (1 + d[f"ffi_{c}"]) * (local_per_usd / local_per_usd.shift(1)) - 1
            i_local = pd.Series(float("nan"), index=d.index)
            for t in LOCAL_RATE_CHAIN:  # first available in this order
                i_local = i_local.combine_first(d[t.format(c=c)])
        carry = (i_eur - i_local.shift(1).reindex(u.index)) / 12
        hedged = r_local.reindex(u.index) + carry - HEDGE_COST
        if c in EURO_MEMBERS:
            hedged[hedged.index >= EURO_START] = u.loc[u.index >= EURO_START, f"eq_{c}"]
        u[f"eqh_{c}"] = hedged

    u["cash"] = base["cash"]
    return u
