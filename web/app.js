"use strict";

const state = { lakes: [], meta: null, date: null, selected: null, readings: {}, chart: null, years: new Set() };
const markers = {};
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const YEAR_COLORS = ["#0b6e99", "#d95f02", "#7570b3", "#1b9e77", "#e7298a", "#66a61e", "#a6761d", "#666666"];

// Reference water year (Jun 1 - May 31, includes 29 Feb) used as the shared x-axis.
const REF_DAYS = (() => {
  const out = [];
  for (let d = new Date(Date.UTC(2023, 5, 1)); d <= new Date(Date.UTC(2024, 4, 31)); d.setUTCDate(d.getUTCDate() + 1))
    out.push(`${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`);
  return out;
})();

const $ = (id) => document.getElementById(id);
const fmtInt = (n) => n.toLocaleString("en-IN");
const fmtPct = (n) => `${n.toFixed(1)}%`;
const api = (path) => fetch(path).then((r) => { if (!r.ok) throw new Error(`${path}: ${r.status}`); return r.json(); });

// Colour bands for percent full. Single source of truth for markers and the legend.
const BANDS = [
  { min: 75, color: "#1f78b4", label: "75% and above" },
  { min: 50, color: "#8cb83a", label: "50 to 75%" },
  { min: 25, color: "#f28e2b", label: "25 to 50%" },
  { min: 0, color: "#d73027", label: "Under 25%" },
];
const colorFor = (pct) => BANDS.find((b) => pct >= b.min).color;

function fillExpression() {
  const asc = [...BANDS].reverse(); // ascending thresholds
  const expr = ["step", ["coalesce", ["get", "percent"], -1], "#888"];
  asc.forEach((b) => expr.push(b.min, b.color));
  return expr;
}

function updateShapes() {
  const map = state.map, src = map && map.getSource("lakes");
  if (!src || !state.geo) return;
  const pct = Object.fromEntries(state.lakes.map((l) => [l.id, l.reading ? l.reading.percent : null]));
  for (const f of state.geo.features) f.properties.percent = pct[f.properties.id];
  src.setData(state.geo);
  map.setFilter("lake-sel", ["==", ["get", "id"], state.selected || ""]);
}

function boundsOf(feature) {
  const pts = feature.geometry.type === "Polygon" ? feature.geometry.coordinates.flat()
    : feature.geometry.coordinates.flat(2);
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  return [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]];
}

function renderLegend() {
  const el = document.createElement("div");
  el.className = "legend";
  el.innerHTML = `<b>Lake full</b>${BANDS.map((b) =>
    `<div><span class="sw" style="background:${b.color}"></span>${b.label}</div>`).join("")}
    <div><span class="sw" style="background:#888"></span>No data</div>
    <small>Marker size = capacity</small>`;
  $("map").appendChild(el);
}
// Water year label: Jun 2025 - May 2026 is "2025-26".
const waterYear = (iso) => { const y = +iso.slice(0, 4); return +iso.slice(5, 7) >= 6 ? y : y - 1; };
const yearLabel = (y) => `${y}-${String(y + 1).slice(2)}`;

async function init() {
  [state.lakes, state.meta] = await Promise.all([api("/api/lakes"), api("/api/meta")]);
  state.date = state.meta.last_date;
  setupMap();
  renderLegend();
  setupDateControls();
  await refresh();
}

function setupMap() {
  const map = new maplibregl.Map({
    container: "map",
    center: [73.2, 19.4],
    zoom: 8.2,
    style: {
      version: 8,
      sources: { osm: { type: "raster", tileSize: 256, maxzoom: 19,
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        attribution: "&copy; <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors" } },
      layers: [{ id: "osm", type: "raster", source: "osm" }],
    },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
  state.map = map;
  map.on("load", async () => {
    state.geo = await api("/api/geometry");
    map.addSource("lakes", { type: "geojson", data: state.geo });
    map.addLayer({ id: "lake-fill", type: "fill", source: "lakes",
      paint: { "fill-color": fillExpression(), "fill-opacity": 0.85 } });
    map.addLayer({ id: "lake-line", type: "line", source: "lakes", paint: { "line-color": "#fff", "line-width": 1 } });
    map.addLayer({ id: "lake-sel", type: "line", source: "lakes", filter: ["==", ["get", "id"], ""],
      paint: { "line-color": "#111", "line-width": 3 } });
    map.on("click", "lake-fill", (e) => select(e.features[0].properties.id));
    map.on("mouseenter", "lake-fill", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "lake-fill", () => (map.getCanvas().style.cursor = ""));
    updateShapes();
  });
  // Close up, the real outline replaces the marker.
  map.on("zoom", () => document.body.classList.toggle("zoomed-in", map.getZoom() >= 11));
  const maxCap = Math.max(...state.lakes.map((l) => l.useful_capacity_ml));
  for (const lake of state.lakes) {
    const el = document.createElement("div");
    el.className = "pin";
    const size = 28 + 34 * Math.sqrt(lake.useful_capacity_ml / maxCap);
    el.style.width = el.style.height = `${size}px`;
    el.title = lake.name;
    el.tabIndex = 0;
    el.setAttribute("role", "button");
    el.addEventListener("click", () => select(lake.id));
    el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") select(lake.id); });
    markers[lake.id] = { el, marker: new maplibregl.Marker({ element: el }).setLngLat([lake.lon, lake.lat]).addTo(map) };
  }
}

function setupDateControls() {
  const first = new Date(state.meta.first_date), last = new Date(state.meta.last_date);
  const span = Math.round((last - first) / 86400000);
  const slider = $("slider"), date = $("date");
  slider.max = span;
  date.min = state.meta.first_date;
  date.max = state.meta.last_date;
  const setFromSlider = () => {
    const d = new Date(first); d.setUTCDate(d.getUTCDate() + +slider.value);
    state.date = d.toISOString().slice(0, 10);
    date.value = state.date;
  };
  slider.addEventListener("input", () => { setFromSlider(); refresh(); });
  date.addEventListener("change", () => {
    if (!date.value) return;
    state.date = date.value;
    slider.value = Math.round((new Date(state.date) - first) / 86400000);
    refresh();
  });
  $("latest").addEventListener("click", () => {
    state.date = state.meta.last_date;
    slider.value = span; date.value = state.date;
    refresh();
  });
  slider.value = span; date.value = state.date;
}

async function refresh() {
  state.lakes = await api(`/api/lakes?date=${state.date}`);
  const summary = await api(`/api/summary?date=${state.date}`);
  renderMarkers();
  updateShapes();
  renderSummary(summary);
  const sims = state.lakes.some((l) => l.reading && l.reading.source === "simulated");
  const days = state.meta.days;
  const banner = $("banner");
  banner.hidden = !(sims || days < 30);
  banner.textContent = sims
    ? "Demo data: these levels are simulated, not real BMC readings."
    : `Early days: ${days} day${days === 1 ? "" : "s"} of real readings so far. History builds up daily.`;
  if (state.selected) renderPanel();
}

function renderMarkers() {
  for (const lake of state.lakes) {
    const el = markers[lake.id].el;
    const pct = lake.reading ? lake.reading.percent : null;
    el.style.background = pct === null ? "#888" : colorFor(pct);
    el.textContent = pct === null ? "?" : Math.round(pct);
    el.classList.toggle("sel", lake.id === state.selected);
    el.classList.toggle("no-outline", !lake.has_outline);
    el.setAttribute("aria-label", `${lake.name}: ${pct === null ? "no data" : fmtPct(pct)} full`);
  }
}

function renderSummary(s) {
  if (!s.current) { $("summary").textContent = "No data for this date"; return; }
  const prev = s.previous_years.map((p) => `${p.year}: ${fmtPct(p.percent)}`).join(" · ");
  $("summary").innerHTML = `<b>${fmtPct(s.current.percent)}</b> full on ${s.current.date}
    (${fmtInt(s.current.storage_ml)} of ${fmtInt(s.total_capacity_ml)} ML)${prev ? `<br>Same day: ${prev}` : ""}`;
}

async function select(id) {
  state.selected = id;
  if (!state.readings[id]) state.readings[id] = await api(`/api/lakes/${id}/readings`);
  const years = [...new Set(state.readings[id].map((r) => waterYear(r.date)))].sort();
  state.years = new Set(years.slice(-3)); // newest three water years by default
  renderMarkers();
  renderPanel();
  const lake = state.lakes.find((l) => l.id === id);
  updateShapes();
  const shape = state.geo && state.geo.features.find((f) => f.properties.id === id);
  if (shape) state.map.fitBounds(boundsOf(shape), { padding: { top: 60, bottom: 60, left: 60, right: 60 }, maxZoom: 13, duration: 700 });
  else state.map.easeTo({ center: [lake.lon, lake.lat], zoom: Math.max(state.map.getZoom(), 10), duration: 600 });
}

function renderPanel() {
  const lake = state.lakes.find((l) => l.id === state.selected);
  const r = lake.reading;
  const series = state.readings[lake.id];
  const allYears = [...new Set(series.map((x) => waterYear(x.date)))].sort();
  const sameDay = sameDayAcrossYears(series, state.date);
  $("panel").innerHTML = `
    <h2>${lake.name}</h2>
    <span class="badge">${lake.system}</span> <span class="badge">${lake.operator}</span>
    ${r ? `<div class="big">${fmtPct(r.percent)}</div>
           <div class="vol">${fmtInt(r.storage_ml)} of ${fmtInt(lake.useful_capacity_ml)} ML on ${r.date}</div>
           <div class="bar"><i style="width:${r.percent}%;background:${colorFor(r.percent)}"></i></div>`
       : `<p class="vol">No reading for this date.</p>`}
    <dl>
      <dt>Built</dt><dd>${lake.built_year}. ${lake.built_note}</dd>
      <dt>River</dt><dd>${lake.river}</dd>
      <dt>District</dt><dd>${lake.district}</dd>
      <dt>Supplies</dt><dd>${fmtInt(lake.supply_mld)} MLD to <b>${lake.serves}</b></dd>
      <dt>Treated at</dt><dd>${lake.treatment_plant} plant (${lake.system})</dd>
      ${lake.feeds_into ? `<dt>Flows into</dt><dd>${state.lakes.find((l) => l.id === lake.feeds_into).name}</dd>` : ""}
    </dl>
    <h3>Storage through the year (Jun to May)</h3>
    <div class="chart-box"><canvas id="chart"></canvas></div>
    <div class="years">${allYears.map((y, i) => `
      <label><input type="checkbox" data-year="${y}" ${state.years.has(y) ? "checked" : ""}>
      <span class="sw" style="background:${YEAR_COLORS[i % YEAR_COLORS.length]}"></span>${yearLabel(y)}</label>`).join("")}</div>
    <h3>Level on ${state.date.slice(5)} in other years</h3>
    ${sameDay.length > 1
      ? `<table><tr><th>Year</th><th>Level</th></tr>
         ${sameDay.map((x) => `<tr><td>${x.year}</td><td>${fmtPct(x.percent)}</td></tr>`).join("")}</table>`
      : `<p class="hint">No earlier years for this lake yet. Per-lake history is not available; see the city-wide
         comparison at the top of the page.</p>`}
    <p class="src">${lake.has_outline ? "Lake outline" : "Approximate lake position (no outline yet)"}${lake.has_outline ? " &copy; OpenStreetMap contributors (ODbL)" : ""}. Facts compiled from public sources; verify before relying on them.</p>`;
  $("panel").querySelectorAll("input[data-year]").forEach((cb) =>
    cb.addEventListener("change", () => {
      cb.checked ? state.years.add(+cb.dataset.year) : state.years.delete(+cb.dataset.year);
      drawChart(series, allYears);
    }));
  drawChart(series, allYears);
}

function sameDayAcrossYears(series, iso) {
  const md = iso.slice(5);
  return series.filter((x) => x.date.slice(5) === md || (md === "02-29" && x.date.slice(5) === "02-28"))
    .map((x) => ({ year: +x.date.slice(0, 4), percent: x.percent }));
}

function drawChart(series, allYears) {
  if (state.chart) state.chart.destroy();
  const sparse = series.length < 60;
  const datasets = allYears.filter((y) => state.years.has(y)).map((y) => {
    const byDay = new Map(series.filter((x) => waterYear(x.date) === y).map((x) => [x.date.slice(5), x.percent]));
    const color = YEAR_COLORS[allYears.indexOf(y) % YEAR_COLORS.length];
    return { label: yearLabel(y), data: REF_DAYS.map((d) => byDay.get(d) ?? null), borderColor: color,
             backgroundColor: color, borderWidth: 1.8, pointRadius: sparse ? 4 : 0, spanGaps: false, tension: 0.15 };
  });
  state.chart = new Chart($("chart"), {
    type: "line",
    data: { labels: REF_DAYS, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false },
        tooltip: { callbacks: { title: (i) => { const [m, d] = REF_DAYS[i[0].dataIndex].split("-"); return `${+d} ${MONTHS[+m - 1]}`; },
                                label: (c) => `${c.dataset.label}: ${c.parsed.y === null ? "-" : fmtPct(c.parsed.y)}` } } },
      scales: {
        y: { min: 0, max: 100, ticks: { callback: (v) => `${v}%` } },
        x: { ticks: { maxRotation: 0, autoSkip: false,
              callback: (v, i) => (REF_DAYS[i].endsWith("-01") ? MONTHS[+REF_DAYS[i].slice(0, 2) - 1] : null) },
             grid: { display: false } },
      },
    },
  });
}

init().catch((e) => { document.getElementById("panel").innerHTML = `<p>Could not load data: ${e.message}</p>`; console.error(e); });
