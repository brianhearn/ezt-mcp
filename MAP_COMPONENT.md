# MAP_COMPONENT.md — EZT MCP Map Component

**Version:** 0.5.0
**Date:** 2026-05-14
**Status:** Concept — not yet specced

---

## Role

The Map Component is a companion component to EZT MCP. It is not part of the MCP server itself. It has three flagship roles: **read-only TS sharing** for human stakeholders, **visual verification** for development/QA of generated territory outputs, and **spatial I/O** for agent-assisted territory work.

Monica (a territory designer working with an agent augmented by EZT MCP) cannot verbalize spatial selections. "Move the ZIP codes along the eastern border of Tom's territory" is ambiguous and error-prone as natural language. She needs to see the map, pan and zoom, identify the parts she cares about, select them, and then tell the agent what to do with that selection.

The Map Component provides that capability. It renders a Territory Solution and, when enabled by context, emits part selections back to the agent. It does not store state, make decisions, or duplicate EZT Designer.

---

## Interaction Model (persistent workspace)

The Map Component is now backed by a **persistent per-user workspace** (ONE active MC session per `user_id`, enforced server-side). `get_map_visualization` is idempotent — it returns the existing session URL if one exists for the user. The MC stays open across multiple operations, workflows, and agent turns. The agent no longer needs to re-send the full TS on every interaction.

```
Agent → (sends TS) → Map Component renders TAL + point layers
Monica selects parts (click / lasso / box)
Map Component → (emits part_ids[]) → Agent
Monica: "move those to Sarah's territory"
Agent calls Realign with the part_ids[] and instruction
Agent → (sends updated TS) → Map Component re-renders
```

The communication contract is simple:
- **Input:** a Territory Solution (TS) — renders one active TAL, dimmed sibling TALs when present, and all point layers
- **Output:** mode-dependent. In `view` mode, no mutation or selection output is emitted. In `select` mode, the component emits an array of `part_ids` the user has chosen.

When a TS contains multiple TALs, the MC must always have exactly one active TAL. The active TAL is selected by `active_tal_id` or TS metadata. Other TALs remain visible as dimmed reference context behind the active TAL; they are not hidden unless a future explicit layer-visibility control says so. In v1, the MC exposes a customer-facing active-alignment selector when multiple TALs are available. Switching alignments updates the map-session state through a browser-safe endpoint and re-renders active/dimmed overlays without requiring the agent to issue a new `get_map_visualization` call. Internal APIs may keep `tal_*` field names, but product chrome must not require customers to understand the acronym “TAL”.

The agent session drives all territory operations. The component is a read/select surface only — it does not call EZT MCP tools directly.

## Live Agent/MCP Communication Model (SSE push + HTTP POST)

- **Persistent session** per user (idempotent `get_map_visualization`).
- **SSE** for server → MC push (mode_changed, tal_updated, job_progress, selection_prompt, session_expired, etc.).
- **HTTP POST** for MC → server events (selection_committed with part_ids, user confirmations, etc.).
- Jobs drive routine state automatically via SSE (no extra agent call for progress or AWAITING_USER_SELECTION transitions).
- Agent calls (`request_part_selection`, `get_part_selection`) are the primary first-class selection API. `set_map_state` is reserved for deliberate low-level control.
- Part layers rendered from static **PMTiles** (one per layer: us_zips.pmtiles, us_counties.pmtiles, etc.). Zoom-gated (centroids ~7-9, full polygons >9). Attributes carried in PMTiles; geometry **never** leaves server in MCP payloads.

Recommended flow:

```
Agent → EZT MCP: create map session for TS + active TAL + mode=select
EZT MCP → Agent: map_url + map_session_id + selection resource URI
Agent subscribes to selection resource and opens/embeds map_url
Monica selects parts and clicks Done
Map Component → EZT MCP web endpoint: selection.committed(part_ids[])
EZT MCP → Agent via MCP resource notification: selection resource changed
Agent calls Analyze / Realign as appropriate
EZT MCP → Map Component live channel: TS updated / refresh needed
```

For OpenClaw specifically, this aligns with MCP Resource Subscriptions: EZT MCP exposes the map-session selection as a subscribable MCP resource, and OpenClaw receives selection commits as MCP notifications in its live event queue. The same pattern should work in other MCP hosts that implement resource subscriptions.

### Map session resources

A map session should be short-lived and customer/API-key scoped. Candidate MCP resources:

- `ezt://part-selections/{selection_task_id}` — committed output of a first-class part-selection task
- `ezt://map-sessions/{map_session_id}/selection` — backward-compatible latest committed selection from the Map Component
- `ezt://map-sessions/{map_session_id}/state` — active TAL, mode, TS identity/revision/hash, expiry, and refresh status

A selection resource update should carry awareness-level data, not full analysis:

```json
{
  "event_type": "selection.committed",
  "map_session_id": "ms_01J...",
  "ts_id": "ts_01HX...",
  "ts_revision": 7,
  "active_tal_id": "tal_revenue",
  "part_layer": "us_zips",
  "part_ids": ["32309", "32308", "32312"],
  "selection_method": "lasso",
  "selected_count": 3,
  "current_assignments": [
    { "territory_id": "T1", "part_ids": ["32309", "32308", "32312"] }
  ]
}
```

The agent should call Analyze for authoritative sales volume, account counts, balance impact, and recommended guidance. Selection notifications should tell the agent what Monica selected, not try to replace analysis. For manual build, the agent should collect territory metadata and call a territory mutation tool such as `create_territory_from_parts`; the MC never creates territories directly.

### Canonical web channel

The Map Component should communicate with EZT MCP over ordinary browser-safe web protocols using only a short-lived map session token or exchange code. The canonical pattern should be:

- fetch initial session state / TS render payload from EZT MCP
- maintain local transient selection while Monica clicks, lassos, boxes, and clears
- emit a single `selection.committed` event only when Monica clicks Done
- listen through SSE or WebSocket for `ts.updated`, `mode.changed`, and `session.expired`

Iframe `postMessage` may still be useful inside OpenClaw Canvas or other host embeds, but it should be an embedding convenience rather than the authoritative cross-system protocol.

---

## Capability Modes

The same component serves sharing and assisted design. Capabilities are enabled or disabled by context, customer licensing, and agent workflow.

### `view` mode — read-only sharing and verification
Used for upper management, Brian/developer verification, QA, and testing. Users can pan, zoom, inspect territories, toggle point layers, view metrics/labels, and read summaries. No selections or edits are emitted. This is analogous to a read-only EZT Designer user: the TS is visible and explorable, but not modifiable.

### `select` mode — agent-assisted spatial selection
Used by Monica or another territory designer during an agent workflow. Includes all `view` capabilities plus part selection primitives. The component emits selected `part_ids[]` to the agent, and the agent decides what MCP tool call to make. Select mode can be used with an existing TS/TAL for realign/analyze workflows, or with only a part layer for manual territory construction and list-return workflows.

### Future `edit` mode — richer direct manipulation
Potential future mode for richer map interactions, still mediated by the agent and MCP tools. Not required for v1.

---

## Part Layer Rendering: PMTiles (new section added above; existing rendering requirements updated below to reference)

Rendering must follow the visual contract in [`DESIGN.md`](DESIGN.md), especially the map-specific tokens for basemap choice, territory fill/stroke opacity, hover/selected states, selected halos, dissolved seams, labels, drawing tools, zoom pill, popups, legends, and z-index ordering.

- Territory polygons — rendered as colored/labeled polygons with visible boundaries using `tokens.map.territory`; default colors come from `tokens.colors.map_territory_palette` unless TS presentation metadata overrides them
- Point layers — rendered as named overlays (e.g., accounts as dots, colored by territory assignment)
- Part boundaries/layers — rendered from **static PMTiles** (zoom-gated as described in dedicated Part Layer Rendering section). Selection operates directly on the overlaid part layer (no separate MCP data fetch for geometry).
- Selection state — selected parts highlighted; count and territory assignment shown using the selected/hover conventions from `DESIGN.md`
- Pan / zoom — standard map navigation plus the sanctioned zoom pill / controls for the chosen chrome variant
- Basemap — default to the `DESIGN.md` dark/light basemap guidance; exact Azure Maps style literals remain a design open question

---

## Product Design System

[`DESIGN.md`](DESIGN.md) is the canonical visual source for the Map Component. It is not a placeholder: as of `DESIGN.md` v0.2.0 it contains Benton's extracted EZT Designer V2 tokens, component rules, hard constraints, and sanctioned map chrome variants.

The Map Component should use `DESIGN.md` for EasyTerritory product chrome: toolbar controls, panels, legends, buttons, empty states, loading states, typography, spacing, semantic colors, focus rings, map labels, territory interaction states, and visual restraint rules.

TS presentation metadata controls solution-specific map symbology. `DESIGN.md` controls the surrounding product look and default visual language. If the two conflict, TS metadata may override data-driven symbology for a specific solution, but it must not introduce new product chrome, fonts, focus behavior, or component language outside `DESIGN.md`.

This separation lets the same component feel like EasyTerritory while still rendering each TS according to its own named views, classifications, and territory styles.

---

## Styling Model

The Map Component must render TS presentation metadata. It should not expose the full EZT Designer symbology editor in v1, but it needs enough styling support for read-only sharing and verification.

V1 styling capabilities:
- Named views / visualization presets inside TS metadata
- Layer visibility toggles
- Territory fill color, stroke color/width, opacity
- Deterministic distinct colors when no explicit style is provided
- Labels from configured feature properties
- Point symbol color, size, shape, and opacity
- Simple classification: categorical unique values, manual breaks, equal interval, quantile
- Legend generation from active style

### Layer-Legend Pattern

When this document refers to Benton's EasyTerritory AI app, it means the `mapsjs/EasyTerritoryAI` repository. The relevant implementation pattern is `easyterritory-portal/src/components/maps/MapLayersPanel.tsx` plus its `LayerClassificationPanel.tsx`, `FiltersPanel.tsx`, and supporting `business-data-layer` / classification utilities.

The MC should follow that app's **Layer-Legend** pattern rather than treating layer visibility and legends as separate UI. One compact panel should show every renderable overlay with its visibility state, symbol/line/fill swatch, label, active/selected row state, and optional expansion for classification entries.

Conceptually, each row is both a layer toggle and its legend entry:

- Visibility checkbox/toggle controls whether the layer renders.
- Icon or swatch previews the effective symbolization for that layer.
- Layer label identifies the overlay: active TAL, reference TALs, point location layers, part overlays, basemap overlays, and future user/custom layers.
- Classification expander appears only when the layer has classified styling.
- Classification sub-rows show class symbol, class label/range, optional filter expression/description, and per-class visibility.
- Data-point and roster-style layers can render inline legends under their layer rows, as Benton’s app does for color and size classification.
- Search can be presented as a layer-panel affordance for business/point layers when searchable fields exist, but search is an exploration/navigation aid, not a TS mutation.
- Settings/edit affordances are not part of MC v1 unless a future spec explicitly adds them; MC can show resolved style state, but should not become a full Designer symbology editor.

This is especially important for point location layers carried in the TS. A TS may contain one or more point layers, each with its own visibility, symbol styling, classification, labels, and simple filter state. The Layer-Legend should make those layers understandable and independently togglable without hiding the territory/alignment context.

Filtering and classification support should be deliberately smaller than Designer but structurally compatible with it:

- Supported v1 classification methods remain categorical unique values, manual breaks, equal interval, and quantile. Benton’s app currently models numeric color and numeric size classes with `quantile` and `equalInterval`, categorical color maps, default/unclassified color, opacity, min zoom, and optional clustering.
- Supported v1 filter state should be simple and declarative: `eq`, `neq`, `in`, `nin`, `lt`, `lte`, `gt`, `gte`, and `between` over point-layer columns, plus visible class toggles. Complex ad hoc query builders are out of scope for MC v1.
- Classification entries may be toggled visible/hidden from the legend. This is a map presentation/filter action, not a TS data mutation.
- Legend class counts/statistics are useful when already present in TS presentation metadata, but MC should not be required to compute heavy statistics client-side.
- Out-of-scale or unavailable layers should remain listed but visually disabled/dimmed rather than disappearing, so users understand why the map changed.

The component should also be able to apply EZT MCP-provided style templates when a TS does not already contain presentation metadata or when the agent asks for a specific context such as `executive_review`, `balance_diagnostic`, or `qa_verification`.

Initial template registry:

- `qa_verification` — development/QA view for generated TS/TAL outputs. Shows diagnostic summary items and may show a debug panel. Useful while debugging geometry, basemap, and render behavior.
- `executive_review` — stakeholder-facing read-only view. Prioritizes clean title/subtitle, concise summary metrics, and legend. Debug is off by default.
- `selection` — spatial input view for Part Selection workflows. Prioritizes user instructions, active layer/context, selected count, and commit/cancel affordances. Debug is off by default.

The upper-left panel is a context panel selected/configured by the resolved presentation template. The agent can provide context (title, subtitle, summary items, legend hints, debug flag) through TS presentation metadata or request-time presentation overrides, but the MC owns layout, typography, and product chrome.

Out of scope for v1 unless later specs add them: full symbology editor, complex filter builder, hotspots, clustering, print layouts, and Designer-level layer administration. These Designer capabilities may still inform TS presentation metadata shape, but MC v1 should only expose resolved layer visibility, simple filters/class visibility, classification legend rows, and point/territory/part overlay toggles.

---

## Selection UX Primitives

- **Click** — toggle a single part in/out of selection
- **Ctrl+Click** — additive single-part selection
- **Lasso** — freehand polygon selection; all parts whose centroid falls inside are selected
- **Box** — rectangular selection
- **Clear** — deselect all

These match the interaction primitives already familiar to EZT Designer users.

---

## Embedding Targets

### Primary: Agent Host Canvas
The component runs as an embedded panel inside the agent's chat interface. During implementation, this is also the primary visual test surface for generated TS/TAL outputs. In OpenClaw this is the Canvas surface. Monica does not leave the conversation — the map appears inline, she views or selects parts depending on mode, and the agent continues.

### Primary Sharing Surface
Read-only TS sharing should use this same component in `view` mode. The agent can launch or embed a read-only view for executives, managers, or QA reviewers. This provides a flagship human-in-the-loop consumption path without creating a second viewer product.

### Secondary: Microsoft Teams Meeting App
A sales ops meeting where Monica and her manager are reviewing territories. The agent is a meeting participant. The map component is embedded as a Teams meeting app (side panel or shared stage). Monica selects parts, the agent (also in the meeting) picks up the selection and narrates or acts on it.

This target is directionally aligned but not in scope for v1.

### Future: Standalone / Embeddable URL
A hosted URL that can be embedded in other surfaces (Power Apps, Dynamics 365, external portals). Requires auth/token model to be defined. Not in scope for v1.

### Development / QA visualization

A minimal read-only MC should ship before deeper geometry tool implementation. The first useful version only needs to render a supplied TS/TAL, fit bounds, show default territory styling/labels, and open in OpenClaw Canvas or a browser. Selection, live refresh, and richer style controls can layer on after this basic verification loop works.

---

## Technology Candidates

| Concern | Candidate | Notes |
|---|---|---|
| Map framework | MapLibre GL JS | Open source, WebGL-based, good polygon/layer performance |
| Part layer tiles | PMTiles | Single-file tile archive; no tile server required; hosted in Azure Blob |
| Basemap | MapLibre default / none | Optional; lightweight |
| Selection engine | MapLibre feature querying | Click and box selection native; lasso requires custom polygon query |
| Communication | MCP Resource Subscriptions + HTTPS/SSE/WebSocket | MV commits selections to EZT MCP; EZT MCP notifies agent through subscribed resources; SSE/WebSocket refreshes MV |

PMTiles note: EasyTerritory's part layer polygons (US ZIPs, counties, states, Canadian FSAs) need to be published as PMTiles archives. This is an operational build task per layer, re-run when canonical part geometry changes. Storage in Azure Blob Storage alongside the MCP infrastructure is the natural home. The first deployed EZT MCP slice has a `us_zips.pmtiles` overlay generated from canonical PostGIS `geo.us_postal` and served as a static browser artifact; it validates the MC overlay contract but should be expanded to production zoom/detail before being treated as the final tile pipeline.

Basemap PMTiles should be treated separately from part-layer PMTiles. The preferred basemap path is an OSM-derived vector PMTiles archive generated through a Protomaps/Planetiler-style pipeline and served from object/blob storage with HTTP Range Request support. This basemap pipeline is independent of geocoding. Customer TS GeoJSON is rendered as an overlay supplied by the agent; it is not baked into PMTiles for v1.

---

## SSE Command Channel (updated)

Server pushes via SSE (one connection per active persistent MC session):
- `mode_changed` (e.g. `select_parts`, `job_progress`, `view_tal`)
- `tal_updated` (with new `tal_id`, TS identity)
- `progress` (best-effort UI hint from `set_map_progress`: `{state, message, percent?}`)
- `job_progress` / `job_complete` / `job_failed` (durable job state remains authoritative)
- `selection_prompt` (for AWAITING_USER_SELECTION jobs)
- `session_expired` / `revoked`

The MC renders `progress` events as a small bottom-center overlay that does not obscure territory geometry. `running` stays visible, `done` briefly flashes success then hides, `error` briefly shows danger styling then hides, and `idle` hides immediately. This is intentionally a live UX indicator only; job/status resources remain the authoritative source for long-running work.

## MC→server Event POSTs (new)

- `selection_committed` : {part_ids: [...], selection_method: "lasso", timestamp}
- Other user actions (confirmation, cancel, etc.).

These drive automatic job advancement (AWAITING_USER_SELECTION → RUNNING) and SSE feedback.

## Selection UX (updated)

Parts rendered from PMTiles layer overlaid on (dimmed) TAL. User can pan/zoom freely, click/lasso/box on visible parts. "Done" button triggers POST of committed part_ids. Open questions resolved where possible (zoom thresholds defined in Part Layer Rendering; geometry never in MCP payloads). Remaining open: exact SSE payload shapes, Teams v2 details.

---

## What This Is Not

- Not a full mapping application — no complex layer management UI, no symbology editor, no print layouts
- Not a replacement for EZT Designer's map — Designer remains the primary visual editing surface for power users
- Not an MCP tool — the component does not call EZT MCP directly; all tool calls go through the agent
- Not stateful — the component holds no territory data between renders; the agent owns the TS

---

*This document is a concept stub. It will be expanded into a full component spec once the Functional Spec and Technical Spec for EZT MCP core are complete.*
