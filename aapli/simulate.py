"""Generate plausible *simulated* daily lake storage so the app can be built
and tested without real data. Rows are tagged source='simulated' and the UI
shows a "Demo data" banner. Never publish simulated rows as real data.

Model (per lake, per day): storage fraction = previous + monsoon inflow - draw,
clamped to [MIN_FRAC, 1.0]. Draw is supply_mld / capacity per day. Each year has
a rain factor (a stand-in for good / poor monsoons) and an onset date; inflow is
spread over ~120 days from onset with a bell-shaped profile plus random bursts.

    python -m aapli.simulate [--db PATH] [--start 2015-10-01] [--end YYYY-MM-DD]
"""
import argparse
import datetime as dt
import math
import random

from .db import connect, db_path, load_lake_facts

MIN_FRAC = 0.02
MONSOON_DAYS = 120
BASE_INFLOW = 1.25  # monsoon inflow as a multiple of capacity in an average year
# Catchment size relative to storage: small lakes fill fast, Modak Sagar lags.
CATCHMENT = {"vihar": 1.8, "tulsi": 1.8, "modak-sagar": 0.9}


def _weights(rng: random.Random) -> list[float]:
    w = []
    for i in range(MONSOON_DAYS):
        x = (i + 0.5) / MONSOON_DAYS
        bell = x**1.2 * (1 - x) ** 1.8
        w.append(bell * rng.lognormvariate(0, 0.8))
    total = sum(w)
    return [v / total for v in w]


def _year_plan(seed: int, year: int, lake_id: str) -> tuple[dt.date, list[float], float]:
    year_rng = random.Random(f"{seed}-{year}")
    rain = min(1.3, max(0.55, year_rng.gauss(1.0, 0.2)))
    onset = dt.date(year, 6, 5) + dt.timedelta(days=year_rng.randint(0, 14))
    lake_rng = random.Random(f"{seed}-{year}-{lake_id}")
    gain = rain * BASE_INFLOW * CATCHMENT.get(lake_id, 1.0) * lake_rng.gauss(1.0, 0.08)
    return onset, _weights(lake_rng), gain


def simulate_lake(lake: dict, start: dt.date, end: dt.date, seed: int = 42):
    """Yield (date, storage_ml) for one lake from start to end inclusive."""
    cap = lake["useful_capacity_ml"]
    draw = lake["supply_mld"] / cap
    frac = 0.95
    plans: dict[int, tuple] = {}
    day = start
    while day <= end:
        if day.year not in plans:
            plans[day.year] = _year_plan(seed, day.year, lake["id"])
        onset, weights, gain = plans[day.year]
        k = (day - onset).days
        inflow = gain * weights[k] if 0 <= k < MONSOON_DAYS else 0.0
        frac = min(1.0, max(MIN_FRAC, frac + inflow - draw))
        yield day, round(frac * cap)
        day += dt.timedelta(days=1)


def run(db: str | None, start: dt.date, end: dt.date, seed: int = 42) -> int:
    facts = load_lake_facts()
    conn = connect(db) if db else connect()
    conn.execute("DELETE FROM readings WHERE source = 'simulated'")
    rows = [
        (d.isoformat(), lake["id"], ml, "simulated")
        for lake in facts["lakes"]
        for d, ml in simulate_lake(lake, start, end, seed)
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO readings (date, lake_id, storage_ml, source) VALUES (?,?,?,?)", rows
    )
    conn.commit()
    conn.close()
    return len(rows)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--db", default=None)
    p.add_argument("--start", default="2015-10-01")
    p.add_argument("--end", default=dt.date.today().isoformat())
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    n = run(a.db, dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end), a.seed)
    print(f"Wrote {n} simulated readings to {a.db or db_path()}")


if __name__ == "__main__":
    main()
