# MAP_COMPONENT.md — EZT MCP Map Component

**Version:** 0.2.0 (stub)
**Date:** 2026-05-06
**Status:** Concept — not yet specced

---

## Role

The Map Component is a companion component to EZT MCP. It is not part of the MCP server itself. It has two flagship roles: **read-only TS sharing** for human stakeholders and **spatial I/O** for agent-assisted territory work.

Monica (a territory designer working with an agent augmented by EZT MCP) cannot verbalize spatial selections. "Move the ZIP codes along the eastern border of Tom's territory" is ambiguous and error-prone as natural language. She needs to see the map, pan and zoom, identify the parts she cares about, select them, and then tell the agent what to do with that selection.

The Map Component provides that capability. It renders a Territory Solution and, when enabled by context, emits part selections back to the agent. It does not store state, make decisions, or duplicate EZT Designer.

---

## Interaction Model

The component is stateless. The agent owns the Territory Solution between interactions.

```
Agent → (sends TS) → Map Component renders TAL + point layers
Monica selects parts (click / lasso / box)
Map Component → (emits part_ids[]) → Agent
Monica: "move those to Sarah's territory"
Agent calls Realign with the part_ids[] and instruction
Agent → (sends updated TS) → Map Component re-renders
```

The communication contract is simple:
- **Input:** a Territory Solution (TS) — renders the optional TAL + all point layers
- **Output:** mode-dependent. In `view` mode, no mutation or selection output is emitted. In `select` mode, the component emits an array of `part_ids` the user has chosen.

The agent session drives all territory operations. The component is a read/select surface only — it does not call EZT MCP tools directly.

---

## Capability Modes

The same component serves sharing and assisted design. Capabilities are enabled or disabled by context, customer licensing, and agent workflow.

### `view` mode — read-only sharing
Used for upper management and verification/testing. Users can pan, zoom, inspect territories, toggle point layers, view metrics/labels, and read summaries. No selections or edits are emitted. This is analogous to a read-only EZT Designer user: the TS is visible and explorable, but not modifiable.

### `select` mode — agent-assisted spatial selection
Used by Monica or another territory designer during an agent workflow. Includes all `view` capabilities plus part selection primitives. The component emits selected `part_ids[]` to the agent, and the agent decides what MCP tool call to make.

### Future `edit` mode — richer direct manipulation
Potential future mode for richer map interactions, still mediated by the agent and MCP tools. Not required for v1.

---

## Rendering Requirements

- Territory polygons — rendered as colored/labeled polygons with visible boundaries
- Point layers — rendered as named overlays (e.g., accounts as dots, colored by territory assignment)
- Part boundaries — rendered as a lighter layer beneath territories so individual ZIPs/counties are selectable
- Selection state — selected parts highlighted; count and territory assignment shown
- Pan / zoom — standard map navigation
- Basemap — optional; lightweight tile basemap or none

---

## Product Design System

The Map Component should use repo-level `DESIGN.md` for EasyTerritory product chrome: toolbar controls, panels, legends, buttons, empty states, loading states, typography, spacing, and semantic colors.

TS presentation metadata controls solution-specific map symbology. `DESIGN.md` controls the surrounding product look and default visual language.

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

The component should also be able to apply EZT MCP-provided style templates when a TS does not already contain presentation metadata or when the agent asks for a specific context such as `executive_review`, `balance_diagnostic`, or `qa_verification`.

Out of scope for v1 unless later specs add them: full symbology editor, complex filter builder, hotspots, clustering, print layouts, and Designer-level layer administration.

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
The component runs as an embedded panel inside the agent's chat interface. In OpenClaw this is the Canvas surface. Monica does not leave the conversation — the map appears inline, she views or selects parts depending on mode, and the agent continues.

### Primary Sharing Surface
Read-only TS sharing should use this same component in `view` mode. The agent can launch or embed a read-only view for executives, managers, or QA reviewers. This provides a flagship human-in-the-loop consumption path without creating a second viewer product.

### Secondary: Microsoft Teams Meeting App
A sales ops meeting where Monica and her manager are reviewing territories. The agent is a meeting participant. The map component is embedded as a Teams meeting app (side panel or shared stage). Monica selects parts, the agent (also in the meeting) picks up the selection and narrates or acts on it.

This target is directionally aligned but not in scope for v1.

### Future: Standalone / Embeddable URL
A hosted URL that can be embedded in other surfaces (Power Apps, Dynamics 365, external portals). Requires auth/token model to be defined. Not in scope for v1.

---

## Technology Candidates

| Concern | Candidate | Notes |
|---|---|---|
| Map framework | MapLibre GL JS | Open source, WebGL-based, good polygon/layer performance |
| Part layer tiles | PMTiles | Single-file tile archive; no tile server required; hosted in Azure Blob |
| Basemap | MapLibre default / none | Optional; lightweight |
| Selection engine | MapLibre feature querying | Click and box selection native; lasso requires custom polygon query |
| Communication | PostMessage / WebSocket / SSE | TBD — depends on embedding host |

PMTiles note: EasyTerritory's part layer polygons (US ZIPs, counties, states, Canadian FSAs) need to be published as PMTiles archives. This is a one-time operational task per layer, re-run when layers are updated. Storage in Azure Blob Storage alongside the MCP infrastructure is the natural home.

Basemap PMTiles should be treated separately from part-layer PMTiles. The preferred basemap path is an OSM-derived vector PMTiles archive generated through a Protomaps/Planetiler-style pipeline and served from object/blob storage with HTTP Range Request support. This basemap pipeline is independent of geocoding. Customer TS GeoJSON is rendered as an overlay supplied by the agent; it is not baked into PMTiles for v1.

---

## Open Questions

1. **Communication protocol** — how does the component post selections back to the agent session? Options: `postMessage` (iframe embed), WebSocket to a lightweight relay, direct SSE channel. The OpenClaw Canvas case and the Teams case may need different mechanisms.

2. **Auth / TS delivery** — how does the component receive the TS securely? Options: agent passes it as an inline payload (size concern for large TSes with many accounts), or agent deposits it at a short-lived signed URL the component fetches. Size of a TS with N point layers needs to be characterized.

3. **PMTiles pipeline** — who owns generation and hosting of part layer PMTiles? Likely Matt Root / infra, but needs to be defined. Tile precision (zoom levels) affects both file size and selection granularity.

4. **Part boundary visibility** — at what zoom level do part boundaries appear? At country zoom, individual ZIP boundaries are noise. Needs a zoom-threshold design.

5. **Teams integration depth** — meeting app vs. tab vs. shared stage. The shared stage scenario (Monica shares the map to all meeting participants) is compelling but requires Teams Live Share or equivalent. Out of scope for v1 but worth noting.

6. **v1 scope** — which embedding target ships first? OpenClaw Canvas is the most tractable (no external platform dependency). Recommend v1 = Canvas only, Teams as v2.

---

## What This Is Not

- Not a full mapping application — no complex layer management UI, no symbology editor, no print layouts
- Not a replacement for EZT Designer's map — Designer remains the primary visual editing surface for power users
- Not an MCP tool — the component does not call EZT MCP directly; all tool calls go through the agent
- Not stateful — the component holds no territory data between renders; the agent owns the TS

---

*This document is a concept stub. It will be expanded into a full component spec once the Functional Spec and Technical Spec for EZT MCP core are complete.*
