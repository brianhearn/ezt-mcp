const statusEl = document.getElementById("status");
const debugEl = document.getElementById("debug");
const debugMessages = [];
let currentPayload = null;
let currentMap = null;
const layerState = {
  territories: true,
  referenceTals: true,
  pointLayers: {},
  pointClasses: {},
};

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
  renderCustomContent(payload);
  renderLayerLegend(payload);
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

function renderCustomContent(payload) {
  const customEl = ensureCustomContentContainer();
  if (!customEl) return;
  const presentation = payload.presentation || {};
  const panel = presentation.panel || {};
  const content = panel.custom_content || presentation.custom_content;
  customEl.innerHTML = "";
  customEl.hidden = !content;
  if (!content) return;

  const title = content.title || content.heading;
  if (title) {
    const h = document.createElement("div");
    h.className = "custom-content-title";
    h.textContent = title;
    customEl.append(h);
  }
  const body = content.text || content.body || content.markdown;
  if (body) {
    const p = document.createElement("div");
    p.className = "custom-content-body";
    p.textContent = body;
    customEl.append(p);
  }
  if (Array.isArray(content.items)) {
    const list = document.createElement("ul");
    list.className = "custom-content-list";
    for (const item of content.items) {
      const li = document.createElement("li");
      if (typeof item === "object" && item !== null) {
        li.textContent = [item.label || item.name, item.value].filter(Boolean).join(": ");
      } else {
        li.textContent = String(item);
      }
      list.append(li);
    }
    customEl.append(list);
  }
}

function ensureCustomContentContainer() {
  let customEl = byId("custom-content");
  if (customEl) return customEl;
  const summaryEl = byId("summary");
  if (!summaryEl || !summaryEl.parentElement) return null;
  customEl = document.createElement("div");
  customEl.id = "custom-content";
  customEl.className = "custom-content";
  customEl.hidden = true;
  summaryEl.insertAdjacentElement("afterend", customEl);
  return customEl;
}

function renderLayerLegend(payload) {
  const legendEl = byId("legend");
  const itemsEl = byId("legend-items");
  if (!legendEl || !itemsEl) return;
  const rows = layerLegendRows(payload);
  legendEl.hidden = !legendVisible(payload) || rows.length === 0;
  itemsEl.innerHTML = "";
  for (const rowDef of rows) itemsEl.append(renderLayerLegendRow(rowDef, payload));
}

function layerLegendRows(payload) {
  const rows = [];
  rows.push({
    kind: "territories",
    id: "territories",
    label: payload.active_tal.label || payload.active_tal.tal_id || "Active territories",
    swatch: defaultTerritorySwatch(payload),
    visible: layerState.territories !== false,
    count: payload.active_tal.territory_count,
    classes: territoryLegendClasses(payload),
  });
  if (hasReferenceTals(payload)) {
    rows.push({
      kind: "referenceTals",
      id: "referenceTals",
      label: chromeLabel(payload, "reference_alignments_legend", "Other alignments (dimmed)"),
      swatch: "#94a3b8",
      visible: layerState.referenceTals !== false,
      count: payload.reference_geojson.features.length,
    });
  }
  for (const layer of Array.isArray(payload.point_layers) ? payload.point_layers : []) {
    ensurePointLayerState(layer);
    rows.push({
      kind: "pointLayer",
      id: layer.point_layer,
      label: layer.label || layer.point_layer,
      swatch: pointLayerColor(layer),
      visible: layerState.pointLayers[layer.point_layer] !== false,
      count: layer.feature_count,
      classes: pointLayerClasses(layer),
      filtered: hasLayerFilters(layer),
      minzoom: layer.minzoom,
      maxzoom: layer.maxzoom,
    });
  }
  for (const layer of Array.isArray(payload.part_layers) ? payload.part_layers : []) {
    rows.push({
      kind: "partLayer",
      id: layer.part_layer,
      label: layer.label || layer.part_layer,
      swatch: "#cbd5e1",
      visible: layer.part_layer === payload.active_part_layer,
      count: null,
      minzoom: layer.minzoom,
    });
  }
  return rows;
}

function renderLayerLegendRow(rowDef, payload) {
  const row = document.createElement("div");
  row.className = `layer-legend-row layer-kind-${rowDef.kind}`;
  row.dataset.layerKind = rowDef.kind;
  row.dataset.layerId = rowDef.id;
  if (!rowDef.visible) row.classList.add("is-hidden-layer");

  const main = document.createElement("div");
  main.className = "layer-legend-main";

  const toggle = document.createElement("input");
  toggle.type = "checkbox";
  toggle.checked = Boolean(rowDef.visible);
  toggle.setAttribute("aria-label", `Toggle ${rowDef.label}`);
  toggle.addEventListener("change", () => toggleLayer(rowDef, toggle.checked));

  const swatch = document.createElement("span");
  swatch.className = rowDef.kind === "pointLayer" ? "legend-swatch point-swatch" : "legend-swatch";
  swatch.style.background = rowDef.swatch || "#2F80ED";

  const labelWrap = document.createElement("div");
  labelWrap.className = "layer-legend-label-wrap";
  const label = document.createElement("span");
  label.className = "layer-legend-label";
  label.textContent = rowDef.label;
  labelWrap.append(label);
  const metaParts = [];
  if (rowDef.count != null) metaParts.push(`${rowDef.count} features`);
  if (rowDef.filtered) metaParts.push("filtered");
  if (rowDef.minzoom != null) metaParts.push(`z${rowDef.minzoom}+`);
  if (rowDef.maxzoom != null) metaParts.push(`≤z${rowDef.maxzoom}`);
  if (metaParts.length) {
    const meta = document.createElement("span");
    meta.className = "layer-legend-meta";
    meta.textContent = metaParts.join(" • ");
    labelWrap.append(meta);
  }

  main.append(toggle, swatch, labelWrap);
  row.append(main);

  if (rowDef.kind === "pointLayer" && Array.isArray(rowDef.classes) && rowDef.classes.length) {
    const classes = document.createElement("div");
    classes.className = "layer-class-list";
    for (const classDef of rowDef.classes) classes.append(renderClassRow(rowDef, classDef));
    row.append(classes);
  }
  return row;
}

function renderClassRow(rowDef, classDef) {
  const row = document.createElement("label");
  row.className = "layer-class-row";
  const toggle = document.createElement("input");
  toggle.type = "checkbox";
  toggle.checked = classVisible(rowDef.id, classDef.id);
  toggle.addEventListener("change", () => togglePointClass(rowDef.id, classDef.id, toggle.checked));
  const swatch = document.createElement("span");
  swatch.className = "legend-swatch";
  swatch.style.background = classDef.color || rowDef.swatch || "#2F80ED";
  const label = document.createElement("span");
  label.textContent = classDef.label || classDef.id;
  row.append(toggle, swatch, label);
  return row;
}

function defaultTerritorySwatch(payload) {
  const item = defaultLegendItems(payload)[0];
  return item && item.color ? item.color : "#2F80ED";
}

function territoryLegendClasses(payload) {
  const presentation = payload.presentation || {};
  if (Array.isArray(presentation.legend_items)) {
    return presentation.legend_items.map((item, index) => ({
      id: String(item.id || item.value || item.label || index),
      label: item.label || item.value || "Territory",
      color: item.color || "#2F80ED",
    }));
  }
  return [];
}

function pointLayerColor(layer) {
  const style = layer.style || {};
  return style.color || style.fill_color || "#00d4aa";
}

function hasLayerFilters(layer) {
  return Boolean((Array.isArray(layer.filters) && layer.filters.length) || layer.filter);
}

function pointLayerClasses(layer) {
  const cls = layer.classification || {};
  const classes = Array.isArray(cls.classes)
    ? cls.classes
    : Array.isArray(cls.breaks) ? cls.breaks : [];
  return classes.map((entry, index) => ({
    id: String(entry.id || entry.value || entry.label || index),
    label: entry.label || formatClassLabel(entry),
    color: entry.color || entry.fill_color || entry.stroke_color || pointLayerColor(layer),
  }));
}

function formatClassLabel(entry) {
  if (entry.label) return entry.label;
  if (entry.value != null) return String(entry.value);
  if (entry.min != null || entry.max != null) {
    return `${entry.min ?? "−∞"}–${entry.max ?? "+∞"}`;
  }
  return "Class";
}

function ensurePointLayerState(layer) {
  const id = layer.point_layer;
  if (layerState.pointLayers[id] == null) {
    layerState.pointLayers[id] = layer.default_visible !== false;
  }
  if (!layerState.pointClasses[id]) layerState.pointClasses[id] = {};
  for (const classDef of pointLayerClasses(layer)) {
    if (layerState.pointClasses[id][classDef.id] == null) {
      layerState.pointClasses[id][classDef.id] = true;
    }
  }
}

function classVisible(layerId, classId) {
  return (
    !layerState.pointClasses[layerId] || layerState.pointClasses[layerId][classId] !== false
  );
}

function toggleLayer(rowDef, visible) {
  if (!currentMap || !currentPayload) return;
  if (rowDef.kind === "territories") layerState.territories = visible;
  if (rowDef.kind === "referenceTals") layerState.referenceTals = visible;
  if (rowDef.kind === "pointLayer") layerState.pointLayers[rowDef.id] = visible;
  if (rowDef.kind === "partLayer") {
    const layer = (currentPayload.part_layers || []).find((item) => item.part_layer === rowDef.id);
    const group = layer && layer.mutually_exclusive_group;
    if (group) {
      currentPayload.active_part_layer = visible ? rowDef.id : null;
    } else {
      layerState.partLayers = layerState.partLayers || {};
      layerState.partLayers[rowDef.id] = visible;
      currentPayload.active_part_layer = visible ? rowDef.id : null;
    }
  }
  applyLayerVisibility(currentMap, currentPayload);
  renderLayerLegend(currentPayload);
}

function togglePointClass(layerId, classId, visible) {
  if (!currentMap || !currentPayload) return;
  layerState.pointClasses[layerId] = layerState.pointClasses[layerId] || {};
  layerState.pointClasses[layerId][classId] = visible;
  updatePointLayerFilters(currentMap, currentPayload);
  renderLayerLegend(currentPayload);
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
    roadMinor:      "#8f8356",
    roadMajor:      "#c8b96f",
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
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 8, 0.22, 12, 0.48],
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
          "line-opacity": 0.56,
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
        "line-color": "#cbd5e1",
        "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.45, 9, 0.85, 12, 1.25],
        "line-opacity": 0.68,
        "line-dasharray": [2.5, 2],
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
}

function applyLayerVisibility(map, payload) {
  for (const layerId of ["territory-fill", "territory-outline", "territory-labels"]) {
    if (map.getLayer(layerId)) map.setLayoutProperty(layerId, "visibility", layerState.territories === false ? "none" : "visible");
  }
  for (const layerId of ["reference-territory-fill", "reference-territory-outline"]) {
    if (map.getLayer(layerId)) map.setLayoutProperty(layerId, "visibility", layerState.referenceTals === false ? "none" : "visible");
  }
  updatePartLayerVisibility(map, payload);
  updatePointLayerFilters(map, payload);
  renderLayerLegend(payload);
}

function partLayerSourceId(partLayerId) { return `part-layer-${partLayerId}`; }
function partLayerBoundaryId(partLayerId) { return `part-layer-${partLayerId}-boundary`; }
function partLayerLabelId(partLayerId) { return `part-layer-${partLayerId}-labels`; }

function addPointLayerSourcesAndLayers(map, payload) {
  const layers = Array.isArray(payload.point_layers) ? payload.point_layers : [];
  if (!layers.length) return;
  if (!map.getSource("points")) {
    map.addSource("points", {
      type: "geojson",
      data: payload.point_geojson || { type: "FeatureCollection", features: [] },
      promoteId: "_render_id",
    });
  }
  for (const layer of layers) {
    ensurePointLayerState(layer);
    const layerId = pointLayerId(layer.point_layer);
    if (map.getLayer(layerId)) continue;
    map.addLayer({
      id: layerId,
      type: "circle",
      source: "points",
      minzoom: layer.minzoom ?? 0,
      maxzoom: layer.maxzoom ?? 24,
      layout: { visibility: layerState.pointLayers[layer.point_layer] === false ? "none" : "visible" },
      paint: {
        "circle-color": pointColorExpression(layer),
        "circle-radius": pointRadiusExpression(layer),
        "circle-opacity": (layer.style && layer.style.opacity) ?? 0.82,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 1,
        "circle-stroke-opacity": 0.72,
      },
      filter: pointLayerFilter(layer),
    });
  }
}

function updatePointLayerFilters(map, payload) {
  const source = map.getSource("points");
  if (source && payload.point_geojson) source.setData(payload.point_geojson);
  for (const layer of Array.isArray(payload.point_layers) ? payload.point_layers : []) {
    ensurePointLayerState(layer);
    const layerId = pointLayerId(layer.point_layer);
    if (!map.getLayer(layerId)) continue;
    map.setLayoutProperty(layerId, "visibility", layerState.pointLayers[layer.point_layer] === false ? "none" : "visible");
    map.setFilter(layerId, pointLayerFilter(layer));
  }
}

function pointLayerId(layerId) { return `point-layer-${layerId}`; }

function pointLayerFilter(layer) {
  const filters = [["==", ["get", "point_layer"], layer.point_layer]];
  for (const predicate of normalizedPredicates(layer.filters || layer.filter)) {
    const expr = predicateExpression(predicate);
    if (expr) filters.push(expr);
  }
  const classExpr = visibleClassExpression(layer);
  if (classExpr) filters.push(classExpr);
  return filters.length === 1 ? filters[0] : ["all", ...filters];
}

function normalizedPredicates(filters) {
  if (!filters) return [];
  if (Array.isArray(filters)) return filters;
  if (typeof filters === "object") return [filters];
  return [];
}

function predicateExpression(predicate) {
  if (!predicate || typeof predicate !== "object") return null;
  const field = predicate.field || predicate.column || predicate.property;
  const op = predicate.op || predicate.operator || "eq";
  const value = predicate.value;
  if (!field) return null;
  const get = ["get", field];
  if (op === "eq") return ["==", get, value];
  if (op === "neq") return ["!=", get, value];
  if (op === "in") return ["in", get, ["literal", Array.isArray(value) ? value : [value]]];
  if (op === "nin") return ["!", ["in", get, ["literal", Array.isArray(value) ? value : [value]]]];
  if (op === "lt") return ["<", ["to-number", get], Number(value)];
  if (op === "lte") return ["<=", ["to-number", get], Number(value)];
  if (op === "gt") return [">", ["to-number", get], Number(value)];
  if (op === "gte") return [">=", ["to-number", get], Number(value)];
  if (op === "between") {
    const min = Array.isArray(value) ? value[0] : predicate.min;
    const max = Array.isArray(value) ? value[1] : predicate.max;
    return ["all", [">=", ["to-number", get], Number(min)], ["<=", ["to-number", get], Number(max)]];
  }
  return null;
}

function visibleClassExpression(layer) {
  const cls = layer.classification || {};
  const field = cls.field || cls.property || cls.column;
  const classes = Array.isArray(cls.classes)
    ? cls.classes
    : Array.isArray(cls.breaks) ? cls.breaks : [];
  const visible = classes.filter((entry, index) => {
    const classId = String(entry.id || entry.value || entry.label || index);
    return classVisible(layer.point_layer, classId);
  });
  if (!field || visible.length === classes.length) return null;
  if (!visible.length) return ["==", ["get", "__never__"], "__hidden__"];
  return ["any", ...visible.map((entry) => classPredicate(field, entry))];
}

function classPredicate(field, entry) {
  const get = ["get", field];
  if (entry.value != null) return ["==", get, entry.value];
  if (Array.isArray(entry.values)) return ["in", get, ["literal", entry.values]];
  const parts = [];
  if (entry.min != null) parts.push([">=", ["to-number", get], Number(entry.min)]);
  if (entry.max != null) parts.push(["<", ["to-number", get], Number(entry.max)]);
  return parts.length > 1 ? ["all", ...parts] : parts[0] || ["==", get, entry.label];
}

function pointColorExpression(layer) {
  const base = pointLayerColor(layer);
  const cls = layer.classification || {};
  const field = cls.field || cls.property || cls.column;
  const classes = Array.isArray(cls.classes)
    ? cls.classes
    : Array.isArray(cls.breaks) ? cls.breaks : [];
  if (!field || !classes.length) return base;
  const categorical = classes.every(
    (entry) => entry.value != null || Array.isArray(entry.values)
  );
  if (categorical) {
    const arms = [];
    for (const entry of classes) {
      const color = entry.color || entry.fill_color || base;
      if (Array.isArray(entry.values)) {
        for (const value of entry.values) arms.push(value, color);
      } else {
        arms.push(entry.value, color);
      }
    }
    return ["match", ["get", field], ...arms, cls.default_color || base];
  }
  const stops = [];
  for (const entry of classes) {
    if (entry.min != null) stops.push(Number(entry.min), entry.color || entry.fill_color || base);
  }
  return stops.length
    ? ["step", ["to-number", ["get", field]], cls.default_color || base, ...stops]
    : base;
}

function pointRadiusExpression(layer) {
  const style = layer.style || {};
  if (typeof style.size === "number") return style.size;
  return ["interpolate", ["linear"], ["zoom"], 3, 3, 9, 5, 13, 7];
}

function addTerritoryLayers(map, payload) {
  try {
    addPartLayerSourcesAndLayers(map, payload);
    addPointLayerSourcesAndLayers(map, payload);
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

  applyLayerVisibility(map, payload);

  for (const layer of Array.isArray(payload.point_layers) ? payload.point_layers : []) {
    const layerId = pointLayerId(layer.point_layer);
    map.on("click", layerId, (event) => showPointPopup(map, event, layer));
    map.on("mouseenter", layerId, () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", layerId, () => { map.getCanvas().style.cursor = ""; });
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

function showPointPopup(map, event, layer) {
  const feature = event.features && event.features[0];
  if (!feature) return;
  const props = feature.properties || {};
  const labelField = layer.label_field || "_render_label";
  const title = props[labelField] || props._render_label || props.label || props.name || props.account_name || layer.label || "Location";
  const rows = Object.entries(props)
    .filter(([key]) => !key.startsWith("_") && !["feature_kind", "point_layer"].includes(key))
    .slice(0, 8)
    .map(([key, value]) => `<div><strong>${escapeHtml(key)}:</strong> ${escapeHtml(value)}</div>`)
    .join("");
  new maplibregl.Popup()
    .setLngLat(event.lngLat)
    .setHTML(`<strong>${escapeHtml(title)}</strong><div class="popup-subtitle">${escapeHtml(layer.label || layer.point_layer)}</div>${rows}`)
    .addTo(map);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
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
    updatePointLayerFilters(currentMap, payload);
    applyLayerVisibility(currentMap, payload);
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
