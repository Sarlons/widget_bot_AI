"""Detailed report of project 2: one self-contained HTML file (charts embedded) + Markdown.

Called by src.globalrank.run_all at the end of the pipeline.
"""
from __future__ import annotations

import base64
import io
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.globalrank.data import EUROPE, NAMES  # noqa: E402
from src.globalrank.features import FEATURES  # noqa: E402

LABELS = {"W": "World buy-and-hold (benchmark)", "US": "US buy-and-hold",
          "EW": "Equal weight, all indexes", "M0": "M0 momentum 12-1 (no model)",
          "M1": "M1 linear ranking model", "M2": "M2 gradient-boosted trees",
          "M3": "M3 neural network"}
COLORS = {"W": "#222222", "US": "#7f7f7f", "EW": "#bcbd22", "M0": "#1f77b4",
          "M1": "#2ca02c", "M2": "#d62728", "M3": "#9467bd"}
CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:980px;margin:24px auto;
padding:0 16px;color:#1d1d1f;line-height:1.5}
h1{font-size:1.7em}h2{margin-top:2em;border-bottom:1px solid #ddd;padding-bottom:4px}
table{border-collapse:collapse;margin:12px 0;font-size:.92em;width:100%}
th,td{border:1px solid #ddd;padding:5px 8px;text-align:right}th{background:#f4f4f6}
td:first-child,th:first-child{text-align:left}img{max-width:100%}
.box{background:#f6f8fa;border-left:4px solid #1f77b4;padding:10px 14px;margin:14px 0}
.warn{border-left-color:#d62728}.small{color:#666;font-size:.9em}
"""


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _img(b64: str, alt: str) -> str:
    return f'<img alt="{alt}" src="data:image/png;base64,{b64}">'


def _pct(x, d=1):
    return "" if pd.isna(x) else f"{x * 100:.{d}f}%"


def _table(rows: list[list], header: list[str]) -> str:
    h = "".join(f"<th>{c}</th>" for c in header)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{h}</tr>{b}</table>"


def _md_table(rows, header) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _wealth_chart(results: dict, title: str) -> str:
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 6.5), sharex=True,
                                 gridspec_kw={"height_ratios": [2, 1]})
    for k, v in results.items():
        w = (1 + v["res"]["ret"]).cumprod()
        a1.plot(w.index, w, label=LABELS[k], color=COLORS[k], lw=2.2 if k in ("W", "M0") else 1.4)
        a2.plot(w.index, -(1 - w / w.cummax()) * 100, color=COLORS[k], lw=1.2)
    a1.set_yscale("log")
    a1.set_ylabel("Wealth of 1 EUR (log scale)")
    a1.set_title(title)
    a1.legend(fontsize=8, frameon=False)
    a1.grid(alpha=.3)
    a2.set_ylabel("Drawdown %")
    a2.grid(alpha=.3)
    return _png(fig)


def _yearly(results: dict) -> pd.DataFrame:
    return pd.DataFrame({k: (1 + v["res"]["ret"]).groupby(v["res"].index.year).prod() - 1
                         for k, v in results.items()})


def _yearly_chart(y: pd.DataFrame, keys) -> str:
    fig, ax = plt.subplots(figsize=(9, 3.6))
    x = np.arange(len(y))
    width = 0.8 / len(keys)
    for i, k in enumerate(keys):
        ax.bar(x + i * width, y[k] * 100, width, label=LABELS[k], color=COLORS[k])
    ax.set_xticks(x + 0.4 - width / 2)
    ax.set_xticklabels(y.index, rotation=90, fontsize=7)
    ax.set_ylabel("Return %")
    ax.axhline(0, color="k", lw=.6)
    ax.legend(fontsize=7, frameon=False, ncol=3)
    ax.grid(axis="y", alpha=.3)
    return _png(fig)


def _holdings_chart(hold: dict, title: str) -> str:
    dates = list(hold)
    assets = sorted({a for h in hold.values() for a in h},
                    key=lambda a: (a not in EUROPE, a))
    m = np.array([[a in hold[T] for T in dates] for a in assets], dtype=float)
    fig, ax = plt.subplots(figsize=(9, 0.28 * len(assets) + 1))
    ax.imshow(m, aspect="auto", cmap="Blues", interpolation="nearest")
    ax.set_yticks(range(len(assets)))
    ax.set_yticklabels([NAMES[a] for a in assets], fontsize=7)
    ticks = [i for i, T in enumerate(dates) if T.month == 12 and T.year % 3 == 0]
    ax.set_xticks(ticks)
    ax.set_xticklabels([dates[i].year + 1 for i in ticks], fontsize=7)
    ax.set_title(title, fontsize=10)
    return _png(fig)


def _importance(feats: dict, labels: dict, T) -> pd.DataFrame:
    """Ridge coefficients and tree permutation importance on the last development fit."""
    from sklearn.inspection import permutation_importance

    from src.globalrank.models import make_model, training_set
    X, y = training_set(feats, labels, T)
    ridge = make_model("M1").fit(X.to_numpy(), y.to_numpy())
    trees = make_model("M2").fit(X.to_numpy(), y.to_numpy())
    pi = permutation_importance(trees, X.to_numpy(), y.to_numpy(), n_repeats=5, random_state=0)
    return pd.DataFrame({"ridge_coef": ridge.coef_, "tree_importance": pi.importances_mean},
                        index=FEATURES)


def _ic(feats: dict, labels: dict, start, end) -> pd.Series:
    """Average monthly rank correlation between each feature and the next 3-month rank."""
    rows = {}
    for t, f in feats.items():
        if start <= t <= end and t in labels and len(f) >= 5:
            y = labels[t].reindex(f.index)
            rows[t] = f.corrwith(y, method="spearman")
    return pd.DataFrame(rows).T.mean()


def write_report(out, universe, dev, test, gate, chosen, dsr, diffs, tdiffs, feats, labels,
                 realised, cash) -> None:
    r, t = dev["results"], test["results"]
    order = [k for k in ("W", "US", "EW", "M0", "M1", "M2", "M3") if k in r]
    torder = [k for k in ("W", "US", "EW", "M0", "M1", "M2", "M3") if k in t]

    def perf_rows(res, keys, d, with_dsr):
        rows = []
        for k in keys:
            m = res[k]["m"]
            diff = "" if k == "W" else f"{d[k][0]:+.2f} [{d[k][1][0]:+.2f}, {d[k][1][1]:+.2f}]"
            row = [LABELS[k], _pct(m["mean_log_ret_ann"], 2), _pct(m["cagr"]), _pct(m["vol_ann"]),
                   f"{m['sharpe']:.2f} ({m['sharpe_se']:.2f})", _pct(m["max_dd"], 0),
                   _pct(m["cvar5_monthly"]), f"{m['turnover_ann']:.2f}", _pct(m["drag_ann"], 2),
                   diff]
            if with_dsr:
                row.append(f"{dsr[k]:.2f}")
            rows.append(row)
        return rows

    header = ["Strategy", "Mean log return/yr", "CAGR", "Volatility", "Sharpe (SE)", "Max drawdown",
              "CVaR 5% (month)", "Turnover/yr", "Cost+tax drag/yr", "Sharpe minus World [95%]"]
    dev_rows = perf_rows(r, order, diffs, True)
    test_rows = perf_rows(t, torder, tdiffs, False)
    ydev = _yearly(r)
    ytest = _yearly(t)
    show = [k for k in ("W", "M0", "M1", "M2", "M3") if k in r]
    best_model = max([k for k in ("M1", "M2", "M3") if k in r],
                     key=lambda k: r[k]["m"]["mean_log_ret_ann"])
    T_last = max(T for T in feats if T <= pd.Timestamp("2021-11-30"))
    imp = _importance(feats, labels, T_last)
    ic = _ic(feats, labels, pd.Timestamp("1995-01-31"), pd.Timestamp("2021-09-30"))

    W, M0 = r["W"]["m"], r["M0"]["m"]
    if chosen:
        verdict = (f"{LABELS[chosen]} passed every development check and was the model taken to "
                   "the 2022-2025 test.")
    else:
        verdict = ("No AI model passed the development checks: none beat both the simple "
                   "momentum rank and world buy-and-hold after costs and tax with a deflated "
                   f"Sharpe of at least 0.95. The 2022-2025 test was run for all models for "
                   "information.")
    tw = t["W"]["m"]
    test_best = max([k for k in torder if k not in ("W", "US", "EW")],
                    key=lambda k: t[k]["m"]["mean_log_ret_ann"])

    summary = [
        verdict,
        f"Development 1995-2021: world buy-and-hold made {_pct(W['mean_log_ret_ann'], 1)} a year "
        f"(log), worst fall {_pct(W['max_dd'], 0)}; momentum M0 made "
        f"{_pct(M0['mean_log_ret_ann'], 1)}, worst fall {_pct(M0['max_dd'], 0)}; the best AI model "
        f"({LABELS[best_model]}) made {_pct(r[best_model]['m']['mean_log_ret_ann'], 1)}, worst fall "
        f"{_pct(r[best_model]['m']['max_dd'], 0)}.",
        f"Test 2022-2025: world buy-and-hold made {_pct(tw['mean_log_ret_ann'], 1)} a year; the best "
        f"ranking strategy ({LABELS[test_best]}) made {_pct(t[test_best]['m']['mean_log_ret_ann'], 1)}.",
        f"{dsr['n_trials']} variants were run in development and are all logged; with that many, "
        f"luck alone would give the best one a Sharpe of about {dsr['sr0_ann']:.2f}.",
    ]

    uni_rows = [[NAMES[c], "Europe" if c in EUROPE else ("Benchmark" if c == "WORLD" else "Other"),
                 f"{a:%Y-%m}", f"{b:%Y-%m}"] for c, (a, b) in universe.items()]
    gate_rows = [[LABELS[k]] + ["yes" if v else "no" for v in g.values()] for k, g in gate.items()]
    gate_header = ["Model"] + list(next(iter(gate.values())).keys()) if gate else []

    charts = {
        "dev_wealth": _wealth_chart({k: r[k] for k in order},
                                    "Development 1995-2021, EUR after costs and tax"),
        "dev_years": _yearly_chart(ydev, show),
        "test_wealth": _wealth_chart({k: t[k] for k in torder},
                                     "Test 2022-2025, EUR after costs and tax"),
        "holdings": _holdings_chart(dev["extra"][best_model]["holdings"],
                                    f"Indexes held by {LABELS[best_model]} (dark = held)"),
        "holdings_m0": _holdings_chart(dev["extra"]["M0"]["holdings"],
                                       "Indexes held by M0 momentum (dark = held)"),
    }
    last_T = max(test["extra"][test_models_key(test)]["holdings"]) if test["extra"] else None
    last_hold = test["extra"][test_models_key(test)]["holdings"][last_T] if last_T else []

    html = [f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>Global Index Ranking</title>"
            f"<style>{CSS}</style></head><body>",
            "<h1>Global index ranking: automated analysis</h1>",
            f"<p class='small'>Generated {date.today():%Y-%m-%d} by "
            "<code>python -m src.globalrank.run_all</code>. Research and education only, not "
            "financial advice. All returns in EUR, after ETF costs and Italian tax.</p>",
            "<div class='box'><b>Summary</b><ul>" + "".join(f"<li>{s}</li>" for s in summary)
            + "</ul></div>",
            "<h2>1. Question and setup</h2>",
            "<p>Each month the bot ranks country stock indexes (14 European, 8 others, and "
            "emerging markets) by their expected return over the next 3 months, holds the top "
            "third in equal weight, and keeps a holding until it drops out of the top half. "
            "The target is to beat buy-and-hold of the developed world (a free proxy for MSCI "
            "World) with a worst fall no larger than the benchmark's. Rules were written down "
            "before any result: <code>docs/globalrank_preregistration.md</code>.</p>",
            "<div class='box warn'>No truly unseen history is left: 2015-2025 was the previous "
            "project's test and 2022-2025 is recent memory. The 2022-2025 test below is a "
            "check, not proof. Every variant run is logged and counted in the deflated Sharpe "
            "ratio.</div>",
            "<h3>Data (all free)</h3>",
            "<p>Country indexes: Kenneth French international country returns (value-weighted, "
            "dividends included, in USD), the US from CRSP, emerging markets and the "
            "developed-world benchmark from French's regional files; converted to EUR with "
            "the project's EUR/USD series; ETF running costs (0.30%/yr, world 0.20%/yr) "
            "deducted. Individual European stocks are not used: free sources list only "
            "today's survivors, which flatters a stock-picking model.</p>",
            _table(uni_rows, ["Index", "Group", "Data from", "Data to"]),
            "<h3>Inputs and models</h3>",
            "<p>Inputs, price-only and ranked across indexes each month: returns over 1, 3, 6 "
            "and 12-1 months, distance from the 12-month high, 12-month volatility, drawdown, "
            "36-month correlation with the world, 12-month trend slope. Models: M0 plain "
            "12-1 momentum rank (no AI); M1 ridge regression; M2 gradient-boosted trees "
            "(LightGBM-style); M3 a small neural network, run only if M2 beats M0. Training "
            "uses only labels whose 3-month window ended at least one month before the "
            "decision (purged walk-forward, expanding window from 1978).</p>",
            "<p>Costs and tax: 0.10% per trade; accumulating UCITS ETFs, so gains are taxed at "
            "26% when sold and ETF losses cannot offset ETF gains (Italian <i>redditi di "
            "capitale</i> vs <i>redditi diversi</i>); everything sold and taxed at the end.</p>",
            "<h2>2. Development results, 1995-2021</h2>",
            _table(dev_rows, header + ["Deflated Sharpe"]),
            "<p class='small'>Sharpe vs EUR cash, standard error in brackets. 'Sharpe minus World' "
            "with a 95% stationary-bootstrap interval (block 12 months). Deflated Sharpe = "
            "probability the true Sharpe is above zero after correcting for all variants "
            "tried.</p>",
            _img(charts["dev_wealth"], "Development wealth and drawdowns"),
            "<h3>Calendar-year returns</h3>", _img(charts["dev_years"], "Yearly returns"),
            "<h3>Development checks (pre-registered)</h3>",
            _table(gate_rows, gate_header) if gate_rows else "",
            f"<p><b>{verdict}</b></p>",
            "<h3>What the models learned</h3>",
            "<p>Average monthly rank correlation between each input and the next 3-month "
            "ranking (1995-2021), and what the models fitted on all data to 2021 rely on:</p>",
            _table([[f, f"{ic.get(f, np.nan):+.3f}", f"{imp.loc[f, 'ridge_coef']:+.3f}",
                     f"{imp.loc[f, 'tree_importance']:.4f}"] for f in FEATURES],
                   ["Input", "Rank correlation with next 3 months", "Linear coefficient",
                    "Tree importance"]),
            _img(charts["holdings_m0"], "Holdings M0"),
            _img(charts["holdings"], "Holdings best model"),
            "<h2>3. Test 2022-2025 (run once)</h2>",
            _table(test_rows, header),
            _img(charts["test_wealth"], "Test wealth and drawdowns"),
            _table([[y] + [_pct(ytest.loc[y, k]) for k in torder] for y in ytest.index],
                   ["Year"] + [LABELS[k] for k in torder]),
            f"<p>Last holdings of the tested ranking strategy (decided {last_T:%Y-%m}): "
            f"{', '.join(NAMES[a] for a in last_hold)}.</p>" if last_T else "",
            "<h2>4. Answers to the two questions</h2>",
            "<p><b>Is European data easier, and is there enough free data?</b> For indexes, yes: "
            "free, survivorship-safe monthly total returns exist for 14 European countries from "
            "1975-1991, enough for this kind of test. For individual European stocks, no: free "
            "sources lack delisted companies, point-in-time index membership and clean "
            "fundamentals, so a stock-level model would be flattered by survivors. Paid data "
            "(several hundred to thousands of euros a year) would be needed.</p>",
            "<p><b>Can it run fully automated?</b> Yes: one command downloads the data, rebuilds "
            "every input point in time, trains the models walk-forward, applies costs and tax, "
            "runs the test and writes this report. In PyCharm, run the module "
            "<code>src.globalrank.run_all</code> with the project's <code>.venv</code> "
            "interpreter; in Claude Code, ask it to run "
            "<code>.venv\\Scripts\\python -m src.globalrank.run_all</code>.</p>",
            "<h2>5. Limits</h2><ul>"
            "<li>Indexes are French's value-weighted country returns, close to but not the same "
            "as MSCI indexes; real UCITS ETFs track MSCI with their own costs and small gaps.</li>"
            "<li>EUR/USD before 1999 uses monthly averages (as in project 1).</li>"
            "<li>Some small markets (Austria, Ireland, New Zealand, Malaysia) have few or no "
            "UCITS ETFs an Italian investor can buy; check availability on Borsa Italiana.</li>"
            "<li>The tax model is a simplification of the Italian rules and should be checked "
            "with a tax adviser.</li>"
            "<li>The 2022-2025 test is short (48 months): a Sharpe ratio has a standard error of "
            "about 0.5 over 4 years.</li></ul>",
            "</body></html>"]
    (out / "report.html").write_text("\n".join(html), encoding="utf-8")

    md = ["# Global index ranking: automated analysis", "",
          f"Generated {date.today():%Y-%m-%d}. Research and education only, not financial "
          "advice. EUR, after ETF costs and Italian tax. Full report with charts: report.html.",
          "", "## Summary", ""] + [f"- {s}" for s in summary] + [
          "", "## Development 1995-2021", "", _md_table(dev_rows, header + ["Deflated Sharpe"]),
          "", "## Development checks", "", _md_table(gate_rows, gate_header) if gate_rows else "",
          "", "## Test 2022-2025 (run once)", "", _md_table(test_rows, header), ""]
    (out / "report.md").write_text("\n".join(md), encoding="utf-8")


def test_models_key(test: dict) -> str:
    """Ranking model shown in the test section: the first one run."""
    return next(iter(test["extra"]))
