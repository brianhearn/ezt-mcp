const statusEl = document.getElementById("status");
const debugEl = document.getElementById("debug");
const debugMessages = [];

function setStatus(message) {
  statusEl.textContent = message;
}

function debugMessage(message, details) {
  const text = details ? `${message}: ${details}` : message;
  debugMessages.push(text);
  console.warn(text);
  if (debugEl) {
    debugEl.hidden = false;
    debugEl.textContent = debugMessages.slice(-8).join("\n");
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
    map.addSource("territories", { type: "geojson", data: payload.geojson });
    map.addLayer({
      id: "territory-fill",
      type: "fill",
      source: "territories",
      paint: {
        "fill-color": ["coalesce", ["get", "_render_color"], "#2F80ED"],
        "fill-opacity": 0.42,
      },
    });
    map.addLayer({
      id: "territory-outline",
      type: "line",
      source: "territories",
      paint: {
        "line-color": "#f6f8fb",
        "line-width": 1.25,
        "line-opacity": 0.85,
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

async function main() {
  const { sessionId, token } = sessionParts();
  if (!sessionId || !token) {
    setStatus("Missing map session token.");
    return;
  }

  const payloadUrl = `${appBaseUrl()}/maps/session/${encodeURIComponent(sessionId)}/${encodeURIComponent(token)}/render-payload`;
  const response = await fetch(payloadUrl);
  if (!response.ok) {
    setStatus(`Failed to load render payload (${response.status}).`);
    return;
  }
  const payload = await response.json();

  document.getElementById("title").textContent = payload.active_tal.label || payload.active_tal.tal_id;
  document.getElementById("subtitle").textContent = payload.active_tal.tal_id;
  document.getElementById("mode").textContent = payload.mode;
  document.getElementById("territory-count").textContent = payload.active_tal.territory_count;
  document.getElementById("revision").textContent = payload.ts_identity.revision;
  document.getElementById("expires").textContent = new Date(payload.expires_at || Date.now()).toLocaleString();

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
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");

  map.on("load", () => {
    debugMessage("Map load event", `features=${payload.geojson && payload.geojson.features ? payload.geojson.features.length : 0}; bounds=${JSON.stringify(payload.bounds)}`);
    addTerritoryLayers(map, payload);
    fitBounds(map, payload.bounds);
    setStatus("Loaded. Debug panel shows map events/errors if present.");
  });

  map.on("styledata", () => {
    debugMessage("Style data loaded");
  });

  map.on("sourcedata", (event) => {
    if (event && event.sourceId && event.isSourceLoaded) {
      debugMessage("Source loaded", event.sourceId);
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
