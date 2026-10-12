import datetime as dt

from aapli.db import load_lake_facts
from aapli.simulate import MIN_FRAC, simulate_lake

START, END = dt.date(2015, 10, 1), dt.date(2018, 10, 1)
LAKES = load_lake_facts()["lakes"]


def test_capacities_sum_to_bmc_total():
    assert sum(l["useful_capacity_ml"] for l in LAKES) == 1447363


def test_deterministic():
    lake = LAKES[0]
    assert list(simulate_lake(lake, START, END, seed=1)) == list(simulate_lake(lake, START, END, seed=1))


def test_bounds_and_daily_coverage():
    for lake in LAKES:
        rows = list(simulate_lake(lake, START, END))
        assert len(rows) == (END - START).days + 1
        cap = lake["useful_capacity_ml"]
        assert all(MIN_FRAC * cap - 1 <= ml <= cap for _, ml in rows)


def test_monsoon_fills_and_summer_drains():
    for lake in LAKES:
        by_day = dict(simulate_lake(lake, START, END))
        cap = lake["useful_capacity_ml"]
        assert by_day[dt.date(2016, 6, 1)] < 0.5 * cap, lake["id"]  # pre-monsoon low
        assert max(v for d, v in by_day.items() if d.year == 2016) > 0.5 * cap, lake["id"]
