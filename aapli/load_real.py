"""Load real readings from data/real/*.csv into the database (idempotent).

    python -m aapli.load_real
"""
import csv

from .db import ROOT, connect, db_path

REAL = ROOT / "data" / "real"


def run(db=None) -> tuple[int, int]:
    conn = connect(db) if db else connect()
    with open(REAL / "readings.csv", newline="", encoding="utf-8") as f:
        rows = [(r["date"], r["lake_id"], int(r["storage_ml"]), r["source"]) for r in csv.DictReader(f)]
    conn.executemany(
        "INSERT OR REPLACE INTO readings (date, lake_id, storage_ml, source) VALUES (?,?,?,?)", rows
    )
    with open(REAL / "reference_totals.csv", newline="", encoding="utf-8") as f:
        refs = [(r["date"], float(r["percent"]), r["source"]) for r in csv.DictReader(f)]
    conn.executemany(
        "INSERT OR REPLACE INTO reference_totals (date, percent, source) VALUES (?,?,?)", refs
    )
    conn.commit()
    conn.close()
    return len(rows), len(refs)


if __name__ == "__main__":
    n, m = run()
    print(f"Loaded {n} readings and {m} reference totals into {db_path()}")
