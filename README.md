# Aapli Lake Levels

An open-source, interactive map of Mumbai's seven supply lakes: current storage,
history, year-on-year comparison, and which parts of the city each lake supplies.
Mumbai first, other Indian cities later.

> **Status: early prototype.** The UI shows **real data only**. Right now that is a
> single day (8 Oct 2026, per lake) plus real city-wide totals for the same date in
> 2025 and 2024, all in `data/real/`. History builds up as daily ingestion is added.
> Lake facts in `data/lakes.json` come from public sources and need verification;
> coordinates are approximate.

## Run it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m aapli.load_real         # loads data/real/*.csv into data/aapli.db
.venv/bin/uvicorn aapli.api:app --port 8000
```

Open http://localhost:8000. Tests: `.venv/bin/python -m pytest`.

Dev only: `python -m aapli.simulate` generates fake history, which the API hides unless
`AAPLI_INCLUDE_SIMULATED=1` is set (the UI then shows a "Demo data" banner).

## Layout

| Path | What |
|---|---|
| `data/real/` | Real readings (CSV) with provenance notes |
| `data/lakes.json` | Static facts per lake: capacity, build year, system, area served |
| `aapli/load_real.py` | Loads the real CSVs into SQLite |
| `aapli/simulate.py` | Dev-only simulated readings (tagged `source='simulated'`) |
| `aapli/db.py` | SQLite schema; readings keyed by (date, lake) |
| `aapli/api.py` | JSON API (`/api/lakes`, `/api/lakes/{id}/readings`, `/api/summary`, `/api/meta`) |
| `data/lakes.geojson` | Lake outlines from OpenStreetMap (ODbL), built by `scripts/build_lake_geometry.py` |
| `web/` | MapLibre + Chart.js frontend on OpenStreetMap tiles |

Simulated data must never be presented or published as real readings.

## Roadmap

1. Real data: daily ingestion of BMC's 6 am report, plus a historical backfill
2. Rainfall layer from IMD gridded data (monsoon vs lake level, El Nino / La Nina years)
3. Lake outlines are in (6 of 7; Middle Vaitarna still needs a source); verified supply areas next
4. Open dataset (CSV) and documented API
5. Other cities / all-India reservoirs

## Licence

Code: MIT. Lake outlines: (c) OpenStreetMap contributors, ODbL. Data licence for readings to be decided before any dataset release.
