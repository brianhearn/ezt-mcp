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

function chromeLabel(payload, key, fallback) {
  const labels = (payload.presentation && payload.presentation.chrome_labels) || {};
  const value = labels[key];
  return typeof value === "string" && value.trim() ? value : fallback;
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
  renderPartLayerControl(payload);
  if (debugEl) debugEl.hidden = !debugEnabled(payload);
}

function panelEyebrow(templateName) {
  if (templateName === "qa_verification") return "QA Verification";
  if (templateName === "selection") return "Part Selection";
  return "Executive Review";
}

function renderTalSwitcher(payload) {
  const { wrapper, select } = ensureTalControl();
  if (!wrapper || !select) return;
  const label = wrapper.querySelector("label");
  if (label) label.textContent = chromeLabel(payload, "active_alignment_label", "Active alignment");
  select.setAttribute("aria-label", chromeLabel(payload, "active_alignment_aria", "Active territory alignment"));
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


function renderPartLayerControl(payload) {
  const { wrapper, select } = ensurePartLayerControl();
  if (!wrapper || !select) return;
  const layers = Array.isArray(payload.part_layers) ? payload.part_layers : [];
  wrapper.hidden = layers.length === 0;
  select.innerHTML = "";

  const none = document.createElement("option");
  none.value = "";
  none.textContent = "No part overlay";
  none.selected = !payload.active_part_layer;
  select.append(none);

  for (const layer of layers) {
    const option = document.createElement("option");
    option.value = layer.part_layer;
    option.textContent = layer.label || layer.part_layer;
    option.selected = layer.part_layer === payload.active_part_layer;
    select.append(option);
  }
}

function ensurePartLayerControl() {
  let wrapper = byId("part-layer-control");
  let select = byId("part-layer-select");
  if (wrapper && select) return { wrapper, select };

  wrapper = document.createElement("div");
  wrapper.className = "tal-control part-layer-control";
  wrapper.id = "part-layer-control";
  wrapper.hidden = true;
  const label = document.createElement("label");
  label.htmlFor = "part-layer-select";
  label.textContent = "Part overlay";
  select = document.createElement("select");
  select.id = "part-layer-select";
  select.setAttribute("aria-label", "Part overlay layer");
  wrapper.append(label, select);
  document.body.append(wrapper);
  attachPartLayerSelectHandler(select);
  return { wrapper, select };
}

function attachPartLayerSelectHandler(select) {
  if (!select || select.dataset.eztPartLayerHandlerAttached === "true") return;
  select.dataset.eztPartLayerHandlerAttached = "true";
  select.addEventListener("change", (event) => {
    setActivePartLayer(event.target.value || null);
  });
}

function setActivePartLayer(partLayerId) {
  if (!currentMap || !currentPayload) return;
  currentPayload.active_part_layer = partLayerId;
  updatePartLayerVisibility(currentMap, currentPayload);
}

function ensureTalControl() {
  let wrapper = byId("tal-control");
  let select = byId("tal-select");
  if (wrapper && select) return { wrapper, select };

  wrapper = document.createElement("div");
  wrapper.className = "tal-control";
  wrapper.id = "tal-control";
  wrapper.hidden = true;
  const label = document.createElement("label");
  label.htmlFor = "tal-select";
  label.textContent = "Active alignment";
  select = document.createElement("select");
  select.id = "tal-select";
  select.setAttribute("aria-label", "Active territory alignment");
  wrapper.append(label, select);
  document.body.append(wrapper);
  attachTalSelectHandler(select);
  return { wrapper, select };
}

function attachTalSelectHandler(select) {
  if (!select || select.dataset.eztTalHandlerAttached === "true") return;
  select.dataset.eztTalHandlerAttached = "true";
  select.addEventListener("change", async (event) => {
    try {
      await switchActiveTal(event.target.value);
    } catch (error) {
      console.error(error);
      debugMessage("Active alignment switch failed", errorDetails(error));
      setStatus(error.message);
      if (currentPayload) renderTalSwitcher(currentPayload);
    }
  });
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
    items.push({ label: chromeLabel(payload, "reference_alignments_legend", "Other alignments (dimmed)"), color: "#94a3b8" });
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

// ─── Theme-aware basemap paint values (from DESIGN.md tokens) ───────────────
const BASEMAP_PAINTS = {
  dark: {
    background:     "#101418",
    earth:          "#11181f",
    landcover:      "#172318",
    landuse:        "#15202a",
    water:          "#172b3a",
    boundary:       "#3b4858",
    roadMinor:      "#334252",
    roadMajor:      "#4d6176",
    building:       "#2d3844",
    buildingOutline:"#465566",
    textPlace:      "#9dafc3",
    textRoad:       "#7f91a6",
    textPoi:        "#8fa1b6",
    halo:           "#101418",
    // territory fill opacity per DESIGN.md
    territoryFill:  0.55,
    territoryLabel: "#f6f8fb",
    territoryLabelHalo: "#101418",
    outlineColor:   "#f6f8fb",
  },
  light: {
    background:     "#f8fafc",
    earth:          "#e8ecef",
    landcover:      "#dde8d8",
    landuse:        "#e5eae8",
    water:          "#b3d4e8",
    boundary:       "#b0bec5",
    roadMinor:      "#cfd8dc",
    roadMajor:      "#b0bec5",
    building:       "#dde2e6",
    buildingOutline:"#c0c9cf",
    textPlace:      "#455a64",
    textRoad:       "#607d8b",
    textPoi:        "#546e7a",
    halo:           "#f8fafc",
    // territory fill opacity per DESIGN.md
    territoryFill:  0.35,
    territoryLabel: "#0f172a",
    territoryLabelHalo: "#f8fafc",
    outlineColor:   "#334155",
  },
};

function resolvedTheme(payload) {
  const t = payload && payload.theme;
  return t === "light" ? "light" : "dark";
}

function applyTheme(payload) {
  document.documentElement.dataset.theme = resolvedTheme(payload);
}

function baseStyle(payload) {
  const theme = resolvedTheme(payload);
  const p = BASEMAP_PAINTS[theme];
  const basemapUrl = payload.basemap && payload.basemap.url;
  const style = {
    version: 8,
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    sources: {},
    layers: [
      { id: "background", type: "background", paint: { "background-color": p.background } },
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
        paint: { "fill-color": p.earth },
      },
      {
        id: "basemap-landcover",
        type: "fill",
        source: "basemap",
        "source-layer": "landcover",
        paint: { "fill-color": p.landcover, "fill-opacity": 0.35 },
      },
      {
        id: "basemap-landuse",
        type: "fill",
        source: "basemap",
        "source-layer": "landuse",
        paint: { "fill-color": p.landuse, "fill-opacity": 0.42 },
      },
      {
        id: "basemap-water",
        type: "fill",
        source: "basemap",
        "source-layer": "water",
        paint: { "fill-color": p.water },
      },
      {
        id: "basemap-boundaries",
        type: "line",
        source: "basemap",
        "source-layer": "boundaries",
        paint: { "line-color": p.boundary, "line-width": 0.7, "line-opacity": 0.55 },
      },
      {
        id: "basemap-roads-minor",
        type: "line",
        source: "basemap",
        "source-layer": "roads",
        minzoom: 8,
        filter: ["!in", "kind", "highway", "major_road"],
        paint: {
          "line-color": p.roadMinor,
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
          "line-color": p.roadMajor,
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
          "fill-color": p.building,
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 11, 0.2, 14, 0.55],
          "fill-outline-color": p.buildingOutline,
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
          "text-color": p.textPlace,
          "text-halo-color": p.halo,
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
          "text-color": p.textRoad,
          "text-halo-color": p.halo,
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
          "text-color": p.textPoi,
          "text-halo-color": p.halo,
          "text-halo-width": 1,
        },
      },
    );
  }
  return style;
}


function addPartLayerSourcesAndLayers(map, payload) {
  const layers = Array.isArray(payload.part_layers) ? payload.part_layers : [];
  for (const layer of layers) {
    const sourceId = partLayerSourceId(layer.part_layer);
    const boundaryId = partLayerBoundaryId(layer.part_layer);
    const labelId = partLayerLabelId(layer.part_layer);
    if (map.getSource(sourceId)) continue;
    map.addSource(sourceId, {
      type: "vector",
      url: `pmtiles://${layer.url}`,
    });
    map.addLayer({
      id: boundaryId,
      type: "line",
      source: sourceId,
      "source-layer": layer.source_layer || "parts",
      minzoom: layer.minzoom ?? 5,
      layout: { visibility: "none" },
      paint: {
        "line-color": "#f8fafc",
        "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.35, 9, 0.75, 12, 1.1],
        "line-opacity": 0.72,
      },
    });
    map.addLayer({
      id: labelId,
      type: "symbol",
      source: sourceId,
      "source-layer": layer.source_layer || "parts",
      minzoom: layer.label_minzoom ?? 8,
      layout: {
        visibility: "none",
        "text-field": ["coalesce", ["get", layer.label_property || "part_id"], ["get", "part_id"], ["get", "partcode"], ""],
        "text-size": ["interpolate", ["linear"], ["zoom"], 8, 9, 12, 11],
        "text-font": ["Noto Sans Regular"],
        "text-allow-overlap": false,
      },
      paint: {
        "text-color": "#e2e8f0",
        "text-halo-color": "#0f172a",
        "text-halo-width": 1.2,
      },
    });
  }
}

function updatePartLayerVisibility(map, payload) {
  const layers = Array.isArray(payload.part_layers) ? payload.part_layers : [];
  for (const layer of layers) {
    const visible = layer.part_layer === payload.active_part_layer ? "visible" : "none";
    for (const layerId of [partLayerBoundaryId(layer.part_layer), partLayerLabelId(layer.part_layer)]) {
      if (map.getLayer(layerId)) map.setLayoutProperty(layerId, "visibility", visible);
    }
  }
  renderPartLayerControl(payload);
}

function partLayerSourceId(partLayerId) { return `part-layer-${partLayerId}`; }
function partLayerBoundaryId(partLayerId) { return `part-layer-${partLayerId}-boundary`; }
function partLayerLabelId(partLayerId) { return `part-layer-${partLayerId}-labels`; }

function addTerritoryLayers(map, payload) {
  try {
    addPartLayerSourcesAndLayers(map, payload);
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
    const tp = BASEMAP_PAINTS[resolvedTheme(payload)];
    map.addLayer({
      id: "territory-fill",
      type: "fill",
      source: "territories",
      paint: {
        "fill-color": ["coalesce", ["get", "_render_color"], "#2F80ED"],
        "fill-opacity": tp.territoryFill,
      },
    });
    map.addLayer({
      id: "territory-outline",
      type: "line",
      source: "territories",
      paint: {
        "line-color": tp.outlineColor,
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
        "symbol-sort-key": ["coalesce", ["to-number", ["get", "_render_label_priority"]], 0],
      },
      paint: {
        "text-color": tp.territoryLabel,
        "text-halo-color": tp.territoryLabelHalo,
        "text-halo-width": 1.5,
      },
    });
  } catch (error) {
    debugMessage("Failed to add territory layers", errorDetails(error));
    throw error;
  }

  updatePartLayerVisibility(map, payload);

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

function ensureProgressOverlay() {
  let overlay = byId("progress-overlay");
  if (overlay) return overlay;

  overlay = document.createElement("div");
  overlay.id = "progress-overlay";
  overlay.style.position = "absolute";
  overlay.style.bottom = "32px";
  overlay.style.left = "50%";
  overlay.style.transform = "translateX(-50%)";
  overlay.style.zIndex = "10";
  overlay.style.minWidth = "220px";
  overlay.style.maxWidth = "420px";
  overlay.style.padding = "8px 14px";
  overlay.style.borderRadius = "8px";
  overlay.style.background = "var(--surface-overlay)";
  overlay.style.border = "1px solid var(--border-default)";
  overlay.style.color = "var(--text-primary)";
  overlay.style.fontSize = "12px";
  overlay.style.backdropFilter = "blur(8px)";
  overlay.style.opacity = "1";
  overlay.style.transition = "opacity 0.2s ease";
  overlay.style.display = "none";

  overlay.innerHTML = `
    <div id="progress-message" style="margin-bottom: 6px; font-weight: 500;"></div>
    <div id="progress-bar-track" style="display: none; margin-top: 6px; height: 3px; border-radius: 999px; background: var(--border-subtle); overflow: hidden;">
      <div id="progress-bar-fill" style="height: 100%; border-radius: 999px; background: var(--brand); transition: width 0.3s ease; width: 0%;"></div>
    </div>
  `;
  document.getElementById("map").appendChild(overlay);
  return overlay;
}

function renderProgress(payload) {
  const overlay = ensureProgressOverlay();
  // reset to idle on any new payload (page refresh, tal switch etc)
  if (!payload || payload.type !== "progress") {
    overlay.style.display = "none";
    return;
  }
  const state = payload.state || "idle";
  const messageEl = document.getElementById("progress-message");
  const trackEl = document.getElementById("progress-bar-track");
  const fillEl = document.getElementById("progress-bar-fill");
  const msg = payload.message || "";

  overlay.classList.remove("progress-done", "progress-error");
  messageEl.textContent = msg;

  if (state === "running") {
    overlay.style.display = "block";
    if (payload.percent != null) {
      trackEl.style.display = "block";
      fillEl.style.width = payload.percent + "%";
    } else {
      trackEl.style.display = "none";
    }
  } else if (state === "done") {
    overlay.classList.add("progress-done");
    trackEl.style.display = "none";
    overlay.style.display = "block";
    setTimeout(() => {
      overlay.style.opacity = "0";
      setTimeout(() => { overlay.style.display = "none"; overlay.style.opacity = "1"; }, 200);
    }, 1500);
  } else if (state === "error") {
    overlay.classList.add("progress-error");
    trackEl.style.display = "none";
    overlay.style.display = "block";
    setTimeout(() => {
      overlay.style.opacity = "0";
      setTimeout(() => { overlay.style.display = "none"; overlay.style.opacity = "1"; }, 200);
    }, 3000);
  } else {
    overlay.style.display = "none";
  }
}

function applyPayload(payload, { refit = true } = {}) {
  currentPayload = payload;
  renderPanel(payload);
  renderProgress(payload); // reset progress to idle when new payload lands
  if (currentMap && currentMap.getSource("territories")) {
    updateTerritoryLayers(currentMap, payload);
    if (refit) fitBounds(currentMap, payload.bounds);
  }
}

async function switchActiveTal(activeTalId) {
  if (!activeTalId || !currentPayload || activeTalId === currentPayload.active_tal.tal_id) return;
  const urls = sessionUrls();
  setStatus(chromeLabel(currentPayload, "switching_active_alignment_status", "Switching active alignment…"));
  const response = await fetch(urls.activeTal, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active_tal_id: activeTalId }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Failed to switch active alignment (${response.status}): ${text}`);
  }
  const payload = await loadPayload();
  applyPayload(payload);
  setStatus(chromeLabel(payload, "active_alignment_updated_status", "Active alignment updated."));
}

async function main() {
  const { sessionId, token } = sessionParts();
  if (!sessionId || !token) {
    setStatus("Missing map session token.");
    return;
  }

  const payload = await loadPayload();
  applyTheme(payload);
  applyPayload(payload, { refit: false });

  attachTalSelectHandler(byId("tal-select"));

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
    setStatus(chromeLabel(payload, "loaded_multi_alignment_status", "Loaded. Use Active alignment to switch layers."));
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

  // SSE event handling for progress (and existing events)
  const eventSource = new EventSource(
    `${appBaseUrl()}/maps/session/${encodeURIComponent(sessionId)}/${encodeURIComponent(token)}/events`
  );
  eventSource.onmessage = function (e) {
    try {
      const event = JSON.parse(e.data);
      handleEvent(event);
    } catch (err) {
      console.warn("SSE parse error", err);
    }
  };
  eventSource.onerror = function () {
    console.warn("SSE connection error - will retry");
  };

  function handleEvent(event) {
    if (!event) return;
    const type = event.type;
    if (type === "progress") {
      renderProgress(event);
    } else if (type === "tal_updated" || type === "mode_changed") {
      loadPayload().then(applyPayload).catch(console.error);
    } else if (type === "selection_prompt") {
      setStatus("Select parts on the map to continue.");
    } else if (type === "part_selection_committed") {
      setStatus("Selection committed. Processing…");
    }
  }
}

main().catch((error) => {
  console.error(error);
  debugMessage("Fatal viewer error", errorDetails(error));
  setStatus(`Error: ${error.message}`);
});
