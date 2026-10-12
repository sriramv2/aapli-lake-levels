"""FastAPI app: JSON API under /api plus the static frontend from web/."""
import datetime as dt
import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from .db import ROOT, connect, include_simulated, load_lake_facts

app = FastAPI(title="Aapli Lake Levels", version="0.1.0")

FACTS = load_lake_facts()
LAKES = {lake["id"]: lake for lake in FACTS["lakes"]}
GEOJSON = ROOT / "data" / "lakes.geojson"
GEOMETRY = json.loads(GEOJSON.read_text()) if GEOJSON.exists() else {"type": "FeatureCollection", "features": []}
for _f in GEOMETRY["features"]:  # outline centres replace the approximate hand-entered coordinates
    LAKES[_f["properties"]["id"]].update(lon=_f["properties"]["center"][0], lat=_f["properties"]["center"][1], has_outline=True)
TOTAL_CAPACITY = sum(lake["useful_capacity_ml"] for lake in LAKES.values())


def _real_only() -> str:
    """SQL fragment hiding simulated rows unless the dev flag is set."""
    return "" if include_simulated() else " AND source != 'simulated'"


def _pct(storage_ml: int, capacity_ml: int) -> float:
    return round(100 * storage_ml / capacity_ml, 2)


def _parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, "date must be YYYY-MM-DD")


def _lake_or_404(lake_id: str) -> dict:
    if lake_id not in LAKES:
        raise HTTPException(404, f"unknown lake '{lake_id}'")
    return LAKES[lake_id]


def _latest_on_or_before(conn, date: str) -> dict[str, dict]:
    rows = conn.execute(
        """SELECT r.lake_id, r.date, r.storage_ml, r.source FROM readings r
           JOIN (SELECT lake_id, MAX(date) AS d FROM readings WHERE date <= ?"""
        + _real_only()
        + """ GROUP BY lake_id) m
             ON m.lake_id = r.lake_id AND m.d = r.date""" + _real_only().replace("source", "r.source"),
        (date,),
    ).fetchall()
    return {r["lake_id"]: dict(r) for r in rows}


@app.get("/api/geometry")
def geometry():
    """Lake outlines (GeoJSON, OpenStreetMap contributors, ODbL)."""
    return GEOMETRY


@app.get("/api/meta")
def meta():
    with connect() as conn:
        row = conn.execute(
            "SELECT MIN(date) a, MAX(date) b, COUNT(*) n, COUNT(DISTINCT date) days FROM readings WHERE 1=1" + _real_only()
        ).fetchone()
        sources = [r[0] for r in conn.execute("SELECT DISTINCT source FROM readings WHERE 1=1" + _real_only())]
    return {
        "first_date": row["a"],
        "last_date": row["b"],
        "readings": row["n"],
        "days": row["days"],
        "sources": sources,
        "total_capacity_ml": TOTAL_CAPACITY,
        "systems": FACTS["systems"],
    }


@app.get("/api/lakes")
def list_lakes(date: str | None = Query(None, description="YYYY-MM-DD; default = latest")):
    with connect() as conn:
        target = _parse_date(date).isoformat() if date else "9999-12-31"
        readings = _latest_on_or_before(conn, target)
    out = []
    for lake in LAKES.values():
        r = readings.get(lake["id"])
        latest = (
            {
                "date": r["date"],
                "storage_ml": r["storage_ml"],
                "percent": _pct(r["storage_ml"], lake["useful_capacity_ml"]),
                "source": r["source"],
            }
            if r
            else None
        )
        out.append({**lake, **FACTS["systems"][lake["system"]], "reading": latest})
    return out


@app.get("/api/lakes/{lake_id}/readings")
def lake_readings(lake_id: str, start: str | None = None, end: str | None = None):
    lake = _lake_or_404(lake_id)
    sql, args = "SELECT date, storage_ml, source FROM readings WHERE lake_id = ?" + _real_only(), [lake_id]
    if start:
        sql += " AND date >= ?"
        args.append(_parse_date(start).isoformat())
    if end:
        sql += " AND date <= ?"
        args.append(_parse_date(end).isoformat())
    with connect() as conn:
        rows = conn.execute(sql + " ORDER BY date", args).fetchall()
    cap = lake["useful_capacity_ml"]
    return [
        {"date": r["date"], "storage_ml": r["storage_ml"], "percent": _pct(r["storage_ml"], cap), "source": r["source"]}
        for r in rows
    ]


@app.get("/api/summary")
def summary(date: str | None = None):
    """Total storage across all lakes on a date, plus the same day in earlier years."""
    with connect() as conn:
        target = _parse_date(date) if date else None
        if target is None:
            last = conn.execute("SELECT MAX(date) FROM readings WHERE 1=1" + _real_only()).fetchone()[0]
            if last is None:
                raise HTTPException(404, "no readings")
            target = dt.date.fromisoformat(last)

        def total_on(day: dt.date):
            readings = _latest_on_or_before(conn, day.isoformat())
            if len(readings) < len(LAKES):
                return None
            ml = sum(r["storage_ml"] for r in readings.values())
            return {"date": day.isoformat(), "storage_ml": ml, "percent": _pct(ml, TOTAL_CAPACITY)}

        def reference_on(day: dt.date):
            r = conn.execute("SELECT percent FROM reference_totals WHERE date = ?", (day.isoformat(),)).fetchone()
            return {"date": day.isoformat(), "storage_ml": None, "percent": r["percent"], "city_total_only": True} if r else None

        current = total_on(target)
        previous = []
        for back in range(1, 6):
            try:
                day = target.replace(year=target.year - back)
            except ValueError:  # 29 Feb
                day = target.replace(year=target.year - back, day=28)
            row = total_on(day) or reference_on(day)
            if row:
                previous.append({"year": day.year, **row})
    return {"total_capacity_ml": TOTAL_CAPACITY, "current": current, "previous_years": previous}


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
