const statusEl = document.getElementById("status");
const debugEl = document.getElementById("debug");
const debugMessages = [];
let currentPayload = null;
let currentMap = null;

function byId(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  const element = byId(id);
  if (element) element.textContent = value == null ? "" : String(value);
}

function setStatus(message) {
  setText("status", message);
}

function debugMessage(message, details) {
  const text = details ? `${message}: ${details}` : message;
  debugMessages.push(text);
  console.warn(text);
  const element = byId("debug");
  if (element && !element.hidden) {
    element.textContent = debugMessages.slice(-8).join("\n");
  }
}

function errorDetails(error) {
  if (!error) return "unknown error";
  if (typeof error === "string") return error;
  if (error.message) return error.message;
  try {
    return JSON.stringify(error);
  } catch (_) {
    return String(error);
  }
}

function styleOverrides(payload) {
  const presentation = payload.presentation || {};
  return presentation.style_overrides || {};
}

function debugEnabled(payload) {
  const presentation = payload.presentation || {};
  const overrides = styleOverrides(payload);
  return Boolean(overrides.debug_panel ?? presentation.debug_panel);
}

function panelVisible(payload) {
  const presentation = payload.presentation || {};
  const overrides = styleOverrides(payload);
  return overrides.show_panel ?? presentation.show_panel ?? true;
}

function legendVisible(payload) {
  const presentation = payload.presentation || {};
  const overrides = styleOverrides(payload);
  return overrides.show_legend ?? presentation.show_legend ?? true;
}

function renderPanel(payload) {
  const presentation = payload.presentation || {};
  const panel = byId("panel");
  if (panel) panel.hidden = !panelVisible(payload);

  setText("panel-eyebrow", presentation.eyebrow || panelEyebrow(presentation.panel_template));
  setText("title", presentation.title || payload.active_tal.label || payload.active_tal.tal_id);
  setText("subtitle", presentation.subtitle || payload.active_tal.tal_id);
  renderTalSwitcher(payload);

  const summaryItems = panelSummaryItems(payload);
  const summaryEl = byId("summary");
  if (!summaryEl) return;
  summaryEl.innerHTML = "";
  for (const item of summaryItems) {
    const dt = document.createElement("dt");
    dt.textContent = item.label;
    const dd = document.createElement("dd");
    dd.textContent = item.value;
    summaryEl.append(dt, dd);
  }
  renderLegend(payload);
  if (debugEl) debugEl.hidden = !debugEnabled(payload);
}

function panelEyebrow(templateName) {
  if (templateName === "qa_verification") return "QA Verification";
  if (templateName === "selection") return "Part Selection";
  return "Executive Review";
}

function renderTalSwitcher(payload) {
  const wrapper = byId("tal-switcher");
  const select = byId("tal-select");
  if (!wrapper || !select) return;
  const tals = Array.isArray(payload.available_tals) ? payload.available_tals : [];
  wrapper.hidden = tals.length <= 1;
  select.innerHTML = "";
  for (const tal of tals) {
    const option = document.createElement("option");
    option.value = tal.tal_id;
    option.textContent = tal.tal_label || tal.tal_id;
    option.selected = tal.tal_id === payload.active_tal.tal_id;
    select.append(option);
  }
}

function panelSummaryItems(payload) {
  const presentation = payload.presentation || {};
  const panel = presentation.panel || {};
  if (Array.isArray(panel.summary_items)) return panel.summary_items.map(normalizeSummaryItem);

  const template = presentation.panel_template || "executive_review";
  const featureCount = payload.geojson && payload.geojson.features ? payload.geojson.features.length : 0;
  const partCount = totalPartCount(payload.geojson);
  const base = [
    { label: "Mode", value: payload.mode },
    { label: "Territories", value: payload.active_tal.territory_count ?? featureCount },
  ];
  if (template === "qa_verification") {
    return [
      ...base,
      { label: "Assigned Parts", value: partCount || "—" },
      { label: "Bounds", value: shortBounds(payload.bounds) },
      { label: "TS Revision", value: payload.ts_identity.revision },
      { label: "Expires", value: new Date(payload.expires_at || Date.now()).toLocaleString() },
    ];
  }
  if (template === "selection") {
    return [
      ...base,
      { label: "Selected", value: "0" },
      { label: "Layer", value: presentation.part_layer || "—" },
      { label: "Expires", value: new Date(payload.expires_at || Date.now()).toLocaleString() },
    ];
  }
  return [
    ...base,
    { label: "Assigned Parts", value: partCount || "—" },
    { label: "TS Revision", value: payload.ts_identity.revision },
  ];
}

function normalizeSummaryItem(item) {
  if (Array.isArray(item)) return { label: String(item[0] || ""), value: String(item[1] ?? "") };
  return { label: String(item.label || item.name || ""), value: String(item.value ?? "") };
}

function totalPartCount(geojson) {
  if (!geojson || !Array.isArray(geojson.features)) return 0;
  let total = 0;
  for (const feature of geojson.features) {
    const props = feature.properties || {};
    try {
      const partIds = typeof props.part_ids === "string" ? JSON.parse(props.part_ids) : props.part_ids;
      if (Array.isArray(partIds)) total += partIds.length;
    } catch (_) {}
  }
  return total;
}

function shortBounds(bounds) {
  if (!Array.isArray(bounds) || bounds.length !== 4) return "—";
  return bounds.map((value) => Number(value).toFixed(2)).join(", ");
}

function renderLegend(payload) {
  const legendEl = byId("legend");
  const itemsEl = byId("legend-items");
  if (!legendEl || !itemsEl) return;
  const presentation = payload.presentation || {};
  const legendItems = Array.isArray(presentation.legend_items)
    ? presentation.legend_items
    : defaultLegendItems(payload);
  legendEl.hidden = !legendVisible(payload) || legendItems.length === 0;
  itemsEl.innerHTML = "";
  for (const item of legendItems) {
    const row = document.createElement("div");
    row.className = "legend-item";
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.background = item.color || "#2F80ED";
    const label = document.createElement("span");
    label.textContent = item.label || item.value || "Territory";
    row.append(swatch, label);
    itemsEl.append(row);
  }
}

function defaultLegendItems(payload) {
  const geojson = payload.geojson;
  if (!geojson || !Array.isArray(geojson.features)) return [];
  const items = geojson.features.slice(0, 8).map((feature) => ({
    label: (feature.properties && (feature.properties._render_label || feature.properties.label)) || "Territory",
    color: (feature.properties && feature.properties._render_color) || "#2F80ED",
  }));
  if (hasReferenceTals(payload)) {
    items.push({ label: "Other TALs (dimmed)", color: "#94a3b8" });
  }
  return items;
}

function hasReferenceTals(payload) {
  return Boolean(
    payload.reference_geojson &&
    Array.isArray(payload.reference_geojson.features) &&
    payload.reference_geojson.features.length
  );
}

function sessionParts() {
  const match = window.location.pathname.match(/\/maps\/session\/([^/]+)(?:\/([^/]+))?/);
  const token = (match && match[2]) || new URLSearchParams(window.location.search).get("token") || "";
  return { sessionId: match ? match[1] : "", token };
}

function baseStyle(payload) {
  const basemapUrl = payload.basemap && payload.basemap.url;
  const style = {
    version: 8,
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    sources: {},
    layers: [
      { id: "background", type: "background", paint: { "background-color": "#101418" } },
    ],
  };

  if (basemapUrl) {
    style.sources.basemap = {
      type: "vector",
      url: `pmtiles://${basemapUrl}`,
    };
    style.layers.push(
      {
        id: "basemap-earth",
        type: "fill",
        source: "basemap",
        "source-layer": "earth",
        paint: { "fill-color": "#11181f" },
      },
      {
        id: "basemap-landcover",
        type: "fill",
        source: "basemap",
        "source-layer": "landcover",
        paint: { "fill-color": "#172318", "fill-opacity": 0.35 },
      },
      {
        id: "basemap-landuse",
        type: "fill",
        source: "basemap",
        "source-layer": "landuse",
        paint: { "fill-color": "#15202a", "fill-opacity": 0.42 },
      },
      {
        id: "basemap-water",
        type: "fill",
        source: "basemap",
        "source-layer": "water",
        paint: { "fill-color": "#172b3a" },
      },
      {
        id: "basemap-boundaries",
        type: "line",
        source: "basemap",
        "source-layer": "boundaries",
        paint: { "line-color": "#3b4858", "line-width": 0.7, "line-opacity": 0.55 },
      },
      {
        id: "basemap-roads-minor",
        type: "line",
        source: "basemap",
        "source-layer": "roads",
        minzoom: 8,
        filter: ["!in", "kind", "highway", "major_road"],
        paint: {
          "line-color": "#334252",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.25, 12, 0.8, 15, 1.4],
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 8, 0.25, 12, 0.65],
        },
      },
      {
        id: "basemap-roads-major",
        type: "line",
        source: "basemap",
        "source-layer": "roads",
        filter: ["in", "kind", "highway", "major_road"],
        paint: {
          "line-color": "#4d6176",
          "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.45, 8, 1.1, 12, 2.4],
          "line-opacity": 0.72,
        },
      },
      {
        id: "basemap-buildings",
        type: "fill",
        source: "basemap",
        "source-layer": "buildings",
        minzoom: 11,
        paint: {
          "fill-color": "#2d3844",
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 11, 0.2, 14, 0.55],
          "fill-outline-color": "#465566",
        },
      },
      {
        id: "basemap-places",
        type: "symbol",
        source: "basemap",
        "source-layer": "places",
        minzoom: 4,
        layout: {
          "text-field": ["coalesce", ["get", "name"], ""],
          "text-size": ["interpolate", ["linear"], ["zoom"], 4, 10, 10, 13],
        },
        paint: {
          "text-color": "#9dafc3",
          "text-halo-color": "#101418",
          "text-halo-width": 1,
        },
      },
      {
        id: "basemap-road-labels",
        type: "symbol",
        source: "basemap",
        "source-layer": "roads",
        minzoom: 11,
        layout: {
          "symbol-placement": "line",
          "text-field": ["coalesce", ["get", "name"], ["get", "ref"], ""],
          "text-size": 10,
        },
        paint: {
          "text-color": "#7f91a6",
          "text-halo-color": "#101418",
          "text-halo-width": 1,
        },
      },
      {
        id: "basemap-pois",
        type: "symbol",
        source: "basemap",
        "source-layer": "pois",
        minzoom: 13,
        layout: {
          "text-field": ["coalesce", ["get", "name"], ""],
          "text-size": 10,
        },
        paint: {
          "text-color": "#8fa1b6",
          "text-halo-color": "#101418",
          "text-halo-width": 1,
        },
      },
    );
  }
  return style;
}

function addTerritoryLayers(map, payload) {
  try {
    map.addSource("reference-territories", {
      type: "geojson",
      data: referenceGeojson(payload),
    });
    map.addSource("territories", { type: "geojson", data: payload.geojson });
    map.addLayer({
      id: "reference-territory-fill",
      type: "fill",
      source: "reference-territories",
      paint: {
        "fill-color": ["coalesce", ["get", "_render_color"], "#94a3b8"],
        "fill-opacity": 0.12,
      },
    });
    map.addLayer({
      id: "reference-territory-outline",
      type: "line",
      source: "reference-territories",
      paint: {
        "line-color": "#94a3b8",
        "line-width": 0.8,
        "line-opacity": 0.32,
      },
    });
    map.addLayer({
      id: "territory-fill",
      type: "fill",
      source: "territories",
      paint: {
        "fill-color": ["coalesce", ["get", "_render_color"], "#2F80ED"],
        "fill-opacity": 0.5,
      },
    });
    map.addLayer({
      id: "territory-outline",
      type: "line",
      source: "territories",
      paint: {
        "line-color": "#f6f8fb",
        "line-width": 1.4,
        "line-opacity": 0.9,
      },
    });
    map.addLayer({
      id: "territory-labels",
      type: "symbol",
      source: "territories",
      layout: {
        "text-field": ["coalesce", ["get", "_render_label"], ["get", "label"], ["get", "territory_id"]],
        "text-size": 12,
        "text-font": ["Noto Sans Regular"],
        "text-allow-overlap": false,
      },
      paint: {
        "text-color": "#f6f8fb",
        "text-halo-color": "#101418",
        "text-halo-width": 1.5,
      },
    });
  } catch (error) {
    debugMessage("Failed to add territory layers", errorDetails(error));
    throw error;
  }

  map.on("click", "territory-fill", (event) => {
    const feature = event.features && event.features[0];
    if (!feature) return;
    const props = feature.properties || {};
    let partCount = 0;
    try {
      const partIds = typeof props.part_ids === "string" ? JSON.parse(props.part_ids) : props.part_ids;
      partCount = Array.isArray(partIds) ? partIds.length : 0;
    } catch (_) {
      partCount = 0;
    }
    new maplibregl.Popup()
      .setLngLat(event.lngLat)
      .setHTML(`<strong>${props.label || props.territory_id || "Territory"}</strong><br/>${props.territory_id || ""}<br/>Parts: ${partCount}`)
      .addTo(map);
  });
  map.on("mouseenter", "territory-fill", () => { map.getCanvas().style.cursor = "pointer"; });
  map.on("mouseleave", "territory-fill", () => { map.getCanvas().style.cursor = ""; });
}

function referenceGeojson(payload) {
  return payload.reference_geojson || { type: "FeatureCollection", features: [] };
}

function updateTerritoryLayers(map, payload) {
  const activeSource = map.getSource("territories");
  const referenceSource = map.getSource("reference-territories");
  if (activeSource) activeSource.setData(payload.geojson);
  if (referenceSource) referenceSource.setData(referenceGeojson(payload));
}

function fitBounds(map, bounds) {
  if (!Array.isArray(bounds) || bounds.length !== 4) return;
  try {
    map.fitBounds([[bounds[0], bounds[1]], [bounds[2], bounds[3]]], {
      padding: 80,
      duration: 0,
      maxZoom: 9,
    });
  } catch (error) {
    debugMessage("Failed to fit bounds", errorDetails(error));
  }
}

function appBaseUrl() {
  return (window.EZT_MCP_BASE_URL || "").replace(/\/$/, "");
}

function sessionUrls() {
  const { sessionId, token } = sessionParts();
  const base = `${appBaseUrl()}/maps/session/${encodeURIComponent(sessionId)}/${encodeURIComponent(token)}`;
  return {
    sessionId,
    token,
    payload: `${base}/render-payload`,
    activeTal: `${base}/active-tal`,
  };
}

async function loadPayload() {
  const urls = sessionUrls();
  const response = await fetch(urls.payload);
  if (!response.ok) {
    throw new Error(`Failed to load render payload (${response.status}).`);
  }
  return response.json();
}

function applyPayload(payload, { refit = true } = {}) {
  currentPayload = payload;
  renderPanel(payload);
  if (currentMap && currentMap.getSource("territories")) {
    updateTerritoryLayers(currentMap, payload);
    if (refit) fitBounds(currentMap, payload.bounds);
  }
}

async function switchActiveTal(activeTalId) {
  if (!activeTalId || !currentPayload || activeTalId === currentPayload.active_tal.tal_id) return;
  const urls = sessionUrls();
  setStatus("Switching active TAL…");
  const response = await fetch(urls.activeTal, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active_tal_id: activeTalId }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Failed to switch active TAL (${response.status}): ${text}`);
  }
  const payload = await loadPayload();
  applyPayload(payload);
  setStatus("Active TAL updated.");
}

async function main() {
  const { sessionId, token } = sessionParts();
  if (!sessionId || !token) {
    setStatus("Missing map session token.");
    return;
  }

  const payload = await loadPayload();
  applyPayload(payload, { refit: false });

  const select = byId("tal-select");
  if (select) {
    select.addEventListener("change", async (event) => {
      try {
        await switchActiveTal(event.target.value);
      } catch (error) {
        console.error(error);
        debugMessage("Active TAL switch failed", errorDetails(error));
        setStatus(error.message);
        if (currentPayload) renderTalSwitcher(currentPayload);
      }
    });
  }

  const protocol = new pmtiles.Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);

  const map = new maplibregl.Map({
    container: "map",
    style: baseStyle(payload),
    center: [-96, 38],
    zoom: 3,
    attributionControl: true,
    failIfMajorPerformanceCaveat: false,
  });
  currentMap = map;
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");

  map.on("load", () => {
    if (debugEnabled(payload)) {
      const features = payload.geojson && payload.geojson.features ? payload.geojson.features.length : 0;
      debugMessage("Map load event", `features=${features}; bounds=${JSON.stringify(payload.bounds)}`);
    }
    addTerritoryLayers(map, payload);
    fitBounds(map, payload.bounds);
    setStatus("Loaded. Use Active TAL to switch layers.");
  });

  map.on("styledata", () => {
    if (debugEnabled(currentPayload || payload)) debugMessage("Style data loaded");
  });

  map.on("sourcedata", (event) => {
    if (event && event.sourceId && event.isSourceLoaded) {
      if (debugEnabled(currentPayload || payload)) debugMessage("Source loaded", event.sourceId);
    }
  });

  map.on("error", (event) => {
    const details = errorDetails(event && event.error ? event.error : event);
    debugMessage("MapLibre error", details);
    setStatus("Map warning/error captured below.");
  });
}

main().catch((error) => {
  console.error(error);
  debugMessage("Fatal viewer error", errorDetails(error));
  setStatus(`Error: ${error.message}`);
});
