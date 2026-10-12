"""Build data/lakes.geojson (lake outlines) from OpenStreetMap.

    .venv/bin/python scripts/build_lake_geometry.py [--refetch]

Fetches the OSM objects below via Overpass (cached in data/raw/osm_lakes.json),
assembles each lake's outline, simplifies it lightly, and writes a GeoJSON file
with the lake id and a representative centre point.

Middle Vaitarna has no named OSM object; it is left out (the app shows a point
marker for it). A candidate source is India-WRIS water bodies.

Geometry (c) OpenStreetMap contributors, ODbL: https://www.openstreetmap.org/copyright
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from shapely.geometry import LineString, Polygon, mapping
from shapely.ops import polygonize, unary_union

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "osm_lakes.json"
OUT = ROOT / "data" / "lakes.geojson"
UA = "aapli-lake-levels/0.1 (open-source hobby project)"

# (osm type, osm id) -> our lake id
OSM = {
    ("relation", 7112404): "bhatsa",
    ("relation", 11799235): "upper-vaitarna",
    ("relation", 1609905): "modak-sagar",
    ("relation", 311633): "vihar",
    ("relation", 6244817): "tulsi",
    ("way", 196507985): "tansa",
}
SIMPLIFY_DEG = 0.0002  # about 20 m


def fetch() -> None:
    rels = ",".join(str(i) for t, i in OSM if t == "relation")
    ways = ",".join(str(i) for t, i in OSM if t == "way")
    query = f"[out:json][timeout:120];(relation(id:{rels});way(id:{ways}););out geom;"
    req = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": UA, "Accept": "application/json"},
    )
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_bytes(urllib.request.urlopen(req, timeout=180).read())


def line(geom) -> LineString:
    return LineString([(p["lon"], p["lat"]) for p in geom])


def assemble(element: dict):
    if element["type"] == "way":
        return Polygon([(p["lon"], p["lat"]) for p in element["geometry"]])
    outer = [line(m["geometry"]) for m in element["members"] if m["role"] == "outer" and m["type"] == "way"]
    inner = [line(m["geometry"]) for m in element["members"] if m["role"] == "inner" and m["type"] == "way"]
    shape = unary_union(list(polygonize(unary_union(outer))))
    if inner:
        shape = shape.difference(unary_union(list(polygonize(unary_union(inner)))))
    return shape


def main() -> None:
    if "--refetch" in sys.argv or not RAW.exists():
        fetch()
    elements = json.loads(RAW.read_text())["elements"]
    features = []
    for el in elements:
        lake_id = OSM[(el["type"], el["id"])]
        shape = assemble(el).simplify(SIMPLIFY_DEG, preserve_topology=True)
        if shape.is_empty:
            raise SystemExit(f"{lake_id}: empty geometry")
        c = shape.representative_point()
        features.append({
            "type": "Feature",
            "properties": {
                "id": lake_id,
                "osm": f"{el['type']}/{el['id']}",
                "center": [round(c.x, 5), round(c.y, 5)],
            },
            "geometry": json.loads(json.dumps(mapping(shape), default=float)),
        })
        print(f"{lake_id:16s} {el['type']}/{el['id']}  type={shape.geom_type}  area~{shape.area * 111 * 111 * 0.945:.1f} km2")
    features.sort(key=lambda f: f["properties"]["id"])
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
