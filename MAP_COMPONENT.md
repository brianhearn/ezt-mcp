# MAP_COMPONENT.md — EZT MCP Map Widget

**Version:** 0.1.0 (stub)
**Date:** 2026-05-05
**Status:** Concept — not yet specced

---

## Role

The Map Widget is a companion component to EZT MCP. It is not part of the MCP server itself. Its purpose is narrow and specific: **it is a spatial I/O device for the agent conversation.**

Monica (a territory designer working with an agent augmented by EZT MCP) cannot verbalize spatial selections. "Move the ZIP codes along the eastern border of Tom's territory" is ambiguous and error-prone as natural language. She needs to see the map, pan and zoom, identify the parts she cares about, select them, and then tell the agent what to do with that selection.

The Map Widget provides that capability. It renders a Territory Solution and emits part selections back to the agent. It does not store state, make decisions, or duplicate EZT Designer.

---

## Interaction Model

The widget is stateless. The agent owns the Territory Solution between interactions.

```
Agent → (sends TS) → Map Widget renders territories + point layers
Monica selects parts (click / lasso / box)
Map Widget → (emits part_ids[]) → Agent
Monica: "move those to Sarah's territory"
Agent calls Realign with the part_ids[] and instruction
Agent → (sends updated TS) → Map Widget re-renders
```

The communication contract is simple:
- **Input:** a Territory Solution (TS) — renders territories layer + all point layers
- **Output:** a selection — an array of `part_ids` the user has chosen

The agent session drives all territory operations. The widget is a read/select surface only — it does not call EZT MCP tools directly.

---

## Rendering Requirements

- Territory polygons — rendered as colored/labeled polygons with visible boundaries
- Point layers — rendered as named overlays (e.g., accounts as dots, colored by territory assignment)
- Part boundaries — rendered as a lighter layer beneath territories so individual ZIPs/counties are selectable
- Selection state — selected parts highlighted; count and territory assignment shown
- Pan / zoom — standard map navigation
- Basemap — optional; lightweight tile basemap or none

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
The widget runs as an embedded panel inside the agent's chat interface. In OpenClaw this is the Canvas surface. Monica does not leave the conversation — the map appears inline, she makes her selection, and the agent continues.

### Secondary: Microsoft Teams Meeting App
A sales ops meeting where Monica and her manager are reviewing territories. The agent is a meeting participant. The map widget is embedded as a Teams meeting app (side panel or shared stage). Monica selects parts, the agent (also in the meeting) picks up the selection and narrates or acts on it.

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

---

## Open Questions

1. **Communication protocol** — how does the widget post selections back to the agent session? Options: `postMessage` (iframe embed), WebSocket to a lightweight relay, direct SSE channel. The OpenClaw Canvas case and the Teams case may need different mechanisms.

2. **Auth / TS delivery** — how does the widget receive the TS securely? Options: agent passes it as an inline payload (size concern for large TSes with many accounts), or agent deposits it at a short-lived signed URL the widget fetches. Size of a TS with N point layers needs to be characterized.

3. **PMTiles pipeline** — who owns generation and hosting of part layer PMTiles? Likely Matt Root / infra, but needs to be defined. Tile precision (zoom levels) affects both file size and selection granularity.

4. **Part boundary visibility** — at what zoom level do part boundaries appear? At country zoom, individual ZIP boundaries are noise. Needs a zoom-threshold design.

5. **Teams integration depth** — meeting app vs. tab vs. shared stage. The shared stage scenario (Monica shares the map to all meeting participants) is compelling but requires Teams Live Share or equivalent. Out of scope for v1 but worth noting.

6. **v1 scope** — which embedding target ships first? OpenClaw Canvas is the most tractable (no external platform dependency). Recommend v1 = Canvas only, Teams as v2.

---

## What This Is Not

- Not a full mapping application — no layer management UI, no symbology editor, no print layouts
- Not a replacement for EZT Designer's map — Designer remains the primary visual editing surface for power users
- Not an MCP tool — the widget does not call EZT MCP directly; all tool calls go through the agent
- Not stateful — the widget holds no territory data between renders; the agent owns the TS

---

*This document is a concept stub. It will be expanded into a full component spec once the Functional Spec and Technical Spec for EZT MCP core are complete.*
