const statusEl = document.getElementById("status");

function setStatus(message) {
  statusEl.textContent = message;
}

function sessionParts() {
  const match = window.location.pathname.match(/\/maps\/session\/([^/]+)/);
  const token = new URLSearchParams(window.location.search).get("token") || "";
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
      { id: "basemap-water", type: "fill", source: "basemap", "source-layer": "water", paint: { "fill-color": "#172532" } },
      { id: "basemap-earth", type: "fill", source: "basemap", "source-layer": "earth", paint: { "fill-color": "#11181f" } },
      { id: "basemap-landuse", type: "fill", source: "basemap", "source-layer": "landuse", paint: { "fill-color": "#15202a", "fill-opacity": 0.45 } },
      { id: "basemap-roads", type: "line", source: "basemap", "source-layer": "roads", paint: { "line-color": "#2f3c4a", "line-width": 0.6, "line-opacity": 0.55 } },
      { id: "basemap-places", type: "symbol", source: "basemap", "source-layer": "places", minzoom: 4, layout: { "text-field": ["coalesce", ["get", "name"], ""], "text-size": 11 }, paint: { "text-color": "#8fa1b6", "text-halo-color": "#101418", "text-halo-width": 1 } },
    );
  }
  return style;
}

function addTerritoryLayers(map, payload) {
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
  map.fitBounds([[bounds[0], bounds[1]], [bounds[2], bounds[3]]], {
    padding: 80,
    duration: 0,
    maxZoom: 9,
  });
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

  const payloadUrl = `${appBaseUrl()}/maps/session/${encodeURIComponent(sessionId)}/render-payload?token=${encodeURIComponent(token)}`;
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
  });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");

  map.on("load", () => {
    addTerritoryLayers(map, payload);
    fitBounds(map, payload.bounds);
    setStatus("Loaded. New-tab view is canonical for v1; inline embedding is experimental.");
  });

  map.on("error", (event) => {
    console.warn("Map error", event && event.error);
    setStatus("Map loaded with warnings. Check browser console for details.");
  });
}

main().catch((error) => {
  console.error(error);
  setStatus(`Error: ${error.message}`);
});
