"""Download all sources and append them to the point-in-time store.

Run:  .venv\\Scripts\\python -m src.ingest.run_all
Safe to run repeatedly: raw files get new timestamps, unchanged records are not duplicated.
"""
from src.ingest import fred, french, french_intl, shiller, worldbank

if __name__ == "__main__":
    for name, module in (("shiller", shiller), ("fred", fred), ("french", french),
                         ("french_intl", french_intl), ("worldbank", worldbank)):
        print(f"{name}: {module.ingest()} new records")
