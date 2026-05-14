# EZT MCP — Agentic Territory Intelligence

> Server-side territory operations for AI agents, backed by EasyTerritory domain expertise.

**Status:** Early implementation/testbed — Vision, Constitution, Scenarios, Functional Spec, and Technical Spec remain active contracts. Initial read-only resources, `query_parts`, Map Component visualization, and async job-control skeletons are implemented for the deploy/test path. See [SDLC.md](SDLC.md) for documentation boundaries, [VISION.md](VISION.md) for product intent, [SCENARIOS.md](SCENARIOS.md) for workflow scenarios, [FUNCTIONAL_SPEC.md](FUNCTIONAL_SPEC.md) for the draft external behavior contract, and [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) for implementation design.

---

## What It Does

EZT MCP is an MCP server that gives AI agents the ability to build, balance, and analyze territory solutions — the same operations that previously required a trained user inside EZT Designer.

**MVP tool surface:**
- **Geocode Address** — address strings → TS with a point layer, using TomTom Level 1 first and Azure Maps fallback
- **Ingest Accounts** — account/location rows → TS point layer, preserving safe non-geometry attributes
- **Direct Build** — explicit part-to-territory assignments + part layer → appended TAL
- **Account Build** — accounts with a grouping attribute (e.g., sales manager) → inferred territory solution with hole-filling and contiguity repair
- **Auto Build** — TS + metric/workload goals + part layer + target territory count → augmented TS with balanced TAL
- **Realign** — move parts between territories in an existing TAL
- **Analyze** — TS-embedded point layers + metrics → structured JSON facts, paired with presentation guidance for agent-generated insight
- **Get Map Visualization** — TS/TAL → browser-safe persistent Map Component URL for read-only review, sharing, QA, and spatial workflows
- **Request Part Selection** — first-class human spatial input: open/switch the MC to a part layer and ask Monica to select parts for build, realign, analyze, or list-return workflows
- **Get Part Selection** — retrieve committed selected part IDs plus awareness metadata from a selection task
- **Create Territory From Parts** — create/update one territory in a TAL from selected part IDs plus agent-collected territory metadata
- **Query Parts** — safe paginated part metadata lookup by filter or explicit part IDs; never returns geometry
- **Set Map State** — deliberate low-level MC state transitions; not the primary selection API
- **Cancel Job** — cooperatively cancel an async EZT MCP job

Output is a **Territory Solution (TS)** — standard GeoJSON and the only geometry-bearing file format used by EZT MCP. A TS supports 0-N point location layers and 0-N territory alignment layers (TALs). Geocode Address returns a TS with a point layer and no TAL; build tools append named TALs so agents and users can compare multiple alignment strategies side by side.

## Architecture

- **Hosted by EasyTerritory** — not self-hosted by customers
- **Durably stateless MCP server** — no customer data persisted as system of record; customer's agent owns territory solution storage
- **Resource Server: PostgreSQL/PostGIS** — part layers (US ZIPs, counties, states, Canadian FSAs), geocode cache, spatial compute support
- **PMTiles/object storage** — vector basemap and part-layer tile archives are static browser-delivery artifacts hosted outside PostgreSQL
- **ExpertPack knowledge layer** — domain expertise for territory design, EZT product knowledge, workflow guidance

## Lifecycle

The repo's SDLC documents and ownership boundaries are defined in [SDLC.md](SDLC.md).

| Phase | Status |
|-------|--------|
| Vision | ✅ Complete |
| Constitution | ✅ Complete |
| Scenario Collection | ✅ Initial registry complete — see [SCENARIOS.md](SCENARIOS.md) |
| Functional Spec | 🟡 Started — see [FUNCTIONAL_SPEC.md](FUNCTIONAL_SPEC.md) |
| Technical Spec | 🟡 Started — see [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) |
| Implementation | 🟡 Started — deploy/testbed slices active |
| Verification | 🟡 Started — unit/schema/smoke gates in place |

## TS Identity and Cache Handles

Every TS should carry `ts_id`, `revision`, `content_hash`, and `updated_at` metadata. Because TS payloads can be many MBs, EZT MCP may support short-lived customer-scoped cache handles so agents can avoid resending the full TS across sequential tool calls. Cache handles are a transport optimization only; the customer's agent/storage remains the system of record.

## DESIGN.md

[`DESIGN.md`](DESIGN.md) is the canonical AI-agent-readable EasyTerritory design system for this repo. As of v0.2.0 it contains Benton's extracted EZT Designer V2 tokens and rules for colors, typography, spacing, components, legends, map callouts, map chrome, territory states, empty/loading/error states, and sanctioned Map Component variants.

Any agent or developer implementing the Map Component should read `DESIGN.md` first. TS presentation metadata may control solution-specific symbology, but `DESIGN.md` controls the EasyTerritory product chrome and default visual language.

## Styling

The lightweight Map Component needs real but bounded styling support. Style should travel with the TS as optional presentation metadata and/or come from EZT MCP style templates. V1 should cover territory colors/boundaries/opacity, labels, point symbols, simple classification, legends, and named visualization presets — enough for sharing and verification without recreating the full Designer symbology surface.

## Analysis Presentation

The Analysis tool returns structured JSON facts. EZT MCP should also expose polished presentation guidance — an MCP resource/prompt or versioned markdown such as `ANALYSIS_DESIGN.md` — so calling agents can turn those facts into useful executive summaries, designer diagnostics, sales-manager action lists, and QA reports.

## Sharing

TS sharing is a flagship feature. EZT MCP should support upper-management consumption without making executives use Designer. Sharing has three lanes: quick review through the Map Component in read-only `view` mode, formal executive reporting through Power BI-friendly projections/exports for the existing EasyTerritory Power BI visual, and interoperability through standard GeoJSON/table exports. Narrative executive summaries can be generated from TS + Analyze output. The customer's agent/storage remains the system of record.

## Map Component

EZT MCP is accompanied by an embedded **Map Component** — a unified TS viewing and spatial I/O component. `get_map_visualization` opens or returns the user's persistent MC workspace. In `view` mode it provides read-only sharing/verification. In `select` mode it supports first-class Part Selection workflows: Monica selects parts visually with click, ctrl-click, lasso, or box; the agent then decides whether to analyze, realign, create a territory, or simply return the selected part list.

Interactive selection should use first-class selection tasks plus MCP Resource Subscriptions: the agent calls `request_part_selection`, opens or reuses the returned map URL, subscribes to `ezt://part-selections/{selection_task_id}`, and receives a notification when Monica clicks Done. The Map Component posts committed selections to EZT MCP over a browser-safe session channel; EZT MCP bridges those commits back to the agent as resource notifications. The MC never creates territories directly — the agent collects territory name/hierarchy/conflict decisions and calls `create_territory_from_parts` or another mutation tool.

Implement the minimal read-only visualization loop early: it is the development/QA feedback surface for validating Direct Build, Realign, Auto Build, Analyze, styling, labels, and hierarchy output. Primary embedding target: OpenClaw Canvas (agent chat interface). Secondary: Microsoft Teams meeting app. Technology candidates: MapLibre GL JS + PMTiles. See [MAP_COMPONENT.md](MAP_COMPONENT.md) for the full concept stub and [DESIGN.md](DESIGN.md) for the required visual system.

## Lineage

Forked/derived from [`brianhearn/ep-mcp`](https://github.com/brianhearn/ep-mcp). Retains the proven FastMCP/Starlette service shape and the EP retrieval engine as the domain knowledge layer. Adds EZT-specific tool, resource, and prompt surfaces on top.

## Deploy/Test Target

The active deploy/test host is the ExpertPack droplet at `165.245.136.51` (`expertpack.ai`). The existing `/mcp` reverse-proxy path can be reused for EZT MCP: `https://expertpack.ai/mcp/` → localhost MCP service on the droplet. This supersedes the old EP MCP testbed role for that path unless a separate path is intentionally introduced later.

## License

Apache 2.0 © 2026 EasyTerritory
