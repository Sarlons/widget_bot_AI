"""Statistical power for Sharpe ratios: how many years of data do we need?

Key formula (Lo 2002, i.i.d. returns): the standard error of an *annualised* Sharpe
ratio SR estimated over Y years is approximately

    SE(SR) = sqrt((1 + SR^2 / 2) / Y)

Minimum Track Record Length (Bailey & Lopez de Prado 2012): number of years needed so
that the observed Sharpe is significantly above a benchmark Sharpe SR0 at confidence
(1 - alpha). With skewness g3 and kurtosis g4 (monthly), it is

    MinTRL = 1 + (1 - g3*sr + (g4-1)/4 * sr^2) * (z / (sr - sr0))^2   [in periods]

where sr, sr0 are per-period (not annualised) Sharpe ratios.

Run:  .venv\\Scripts\\python -m src.validation.power
"""
from __future__ import annotations

import math

from scipy.stats import norm


def sharpe_se(sr_annual: float, years: float) -> float:
    """Approximate SE of an annualised Sharpe ratio (i.i.d. normal returns)."""
    return math.sqrt((1 + sr_annual ** 2 / 2) / years)


def min_track_record_years(sr_annual: float, sr0_annual: float = 0.0, alpha: float = 0.05,
                           skew: float = 0.0, kurt: float = 3.0,
                           periods_per_year: int = 12) -> float:
    """Years of data needed to say SR > SR0 at level alpha (one-sided).

    skew/kurt are of the per-period returns (normal: 0 and 3). Equity monthly returns
    typically have skew ~ -0.5 and kurtosis ~ 5, which lengthens the requirement.
    """
    if sr_annual <= sr0_annual:
        return math.inf
    sr = sr_annual / math.sqrt(periods_per_year)
    sr0 = sr0_annual / math.sqrt(periods_per_year)
    z = norm.ppf(1 - alpha)
    n = 1 + (1 - skew * sr + (kurt - 1) / 4 * sr ** 2) * (z / (sr - sr0)) ** 2
    return n / periods_per_year


def main() -> None:
    print("SE of annualised Sharpe ratio")
    print(f"{'SR':>5} " + " ".join(f"{y:>7}y" for y in (10, 20, 50, 88)))
    for sr in (0.2, 0.4, 0.6, 1.0):
        print(f"{sr:>5.1f} " + " ".join(f"{sharpe_se(sr, y):>8.3f}" for y in (10, 20, 50, 88)))

    print("\nMinimum track record (years) to show SR > SR0 at 95%, monthly data")
    print("  normal returns | equity-like (skew -0.5, kurt 5)")
    for sr, sr0 in ((0.4, 0.0), (0.6, 0.4), (0.5, 0.3), (0.8, 0.4)):
        a = min_track_record_years(sr, sr0)
        b = min_track_record_years(sr, sr0, skew=-0.5, kurt=5.0)
        print(f"  SR={sr:.1f} vs SR0={sr0:.1f}: {a:6.1f}  | {b:6.1f}")


if __name__ == "__main__":
    main()
