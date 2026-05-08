# EZT MCP — Agentic Territory Intelligence

> Server-side territory operations for AI agents, backed by EasyTerritory domain expertise.

**Status:** Pre-implementation — Vision and Constitution in active revision. See [VISION.md](VISION.md) for product intent.

---

## What It Does

EZT MCP is an MCP server that gives AI agents the ability to build, balance, and analyze territory solutions — the same operations that previously required a trained user inside EZT Designer.

**MVP tools:**
- **Geocode Address** — address strings → TS with a point layer, using TomTom Level 1 first and Azure Maps fallback
- **Direct Build** — alignment file (ZIP code → territory name mapping) + part layer → territory solution
- **Account Build** — accounts with a grouping attribute (e.g., sales manager) → inferred territory solution with hole-filling and contiguity repair
- **Auto Build** — TS + metric + part layer + target territory count → augmented TS with balanced TAL
- **Realign** — move parts between territories (or into a new territory) in an existing solution
- **Analyze Territory Solution** — TS-embedded point layers + metrics → structured JSON analysis, paired with presentation guidance for agent-generated insight

Output is a **Territory Solution (TS)** — standard GeoJSON and the only geometry-bearing file format used by EZT MCP. A TS supports 0-N point location layers and 0-N territory alignment layers (TALs). Geocode Address returns a TS with a point layer and no TAL; build tools append named TALs so agents and users can compare multiple alignment strategies side by side.

## Architecture

- **Hosted by EasyTerritory** — not self-hosted by customers
- **Durably stateless MCP server** — no customer data persisted as system of record; customer's agent owns territory solution storage
- **Resource Server: PostgreSQL/PostGIS** — part layers (US ZIPs, counties, states, Canadian FSAs), geocode cache, spatial compute support
- **PMTiles/object storage** — vector basemap and part-layer tile archives are static browser-delivery artifacts hosted outside PostgreSQL
- **ExpertPack knowledge layer** — domain expertise for territory design, EZT product knowledge, workflow guidance

## Lifecycle

| Phase | Status |
|-------|--------|
| Vision | ✅ Complete |
| Constitution | ✅ Complete |
| Functional Spec | 🔲 Not started |
| Technical Spec | 🔲 Not started |
| Implementation | 🔲 Not started |
| Verification | 🔲 Not started |

## TS Identity and Cache Handles

Every TS should carry `ts_id`, `revision`, `content_hash`, and `updated_at` metadata. Because TS payloads can be many MBs, EZT MCP may support short-lived customer-scoped cache handles so agents can avoid resending the full TS across sequential tool calls. Cache handles are a transport optimization only; the customer's agent/storage remains the system of record.

## DESIGN.md

The repo includes `DESIGN.md`, a scaffold for an AI-agent-readable EasyTerritory design system derived from Benton's EZT Designer V2 work. It should be populated with tokens and guidance for colors, typography, spacing, components, legends, map callouts, and product chrome so the EZT MCP Map Component stays visually consistent with the broader product stack.

## Styling

The lightweight Map Component needs real but bounded styling support. Style should travel with the TS as optional presentation metadata and/or come from EZT MCP style templates. V1 should cover territory colors/boundaries/opacity, labels, point symbols, simple classification, legends, and named visualization presets — enough for sharing and verification without recreating the full Designer symbology surface.

## Analysis Presentation

The Analysis tool returns structured JSON facts. EZT MCP should also expose polished presentation guidance — an MCP resource/prompt or versioned markdown such as `ANALYSIS_DESIGN.md` — so calling agents can turn those facts into useful executive summaries, designer diagnostics, sales-manager action lists, and QA reports.

## Sharing

TS sharing is a flagship feature. EZT MCP should support upper-management consumption without making executives use Designer. The primary sharing surface is the same Map Component used for assisted workflows, running in read-only `view` mode. Additional sharing modes are Power BI-friendly projections/exports and narrative executive summaries generated from TS + Analyze output. The customer's agent/storage remains the system of record.

## Map Component

EZT MCP is accompanied by an embedded **Map Component** — a unified TS viewing and spatial I/O component. In `view` mode it provides read-only sharing/verification. In `select` mode it emits part selections (click, lasso, box) back to the agent. Monica selects parts visually; the agent calls Realign with the selection. The component is stateless — the agent owns the TS between interactions.

Primary embedding target: OpenClaw Canvas (agent chat interface). Secondary: Microsoft Teams meeting app. Technology candidates: MapLibre GL JS + PMTiles. See [MAP_COMPONENT.md](MAP_COMPONENT.md) for the full concept stub.

## Lineage

Forked from [`brianhearn/ep-mcp`](https://github.com/brianhearn/ep-mcp). Retains the EP MCP retrieval engine as the domain knowledge layer. Adds EZT-specific tool, resource, and prompt surfaces on top.

## License

Apache 2.0 © 2026 EasyTerritory
