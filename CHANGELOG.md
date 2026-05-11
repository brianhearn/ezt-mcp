# CHANGELOG

All notable changes to EZT MCP are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Changed (2026-05-11) — v0.12.0 (CONSTITUTION) / v0.6.0 (SCENARIOS)
- `CONSTITUTION.md` v0.12.0 — major expansion of Section 2.10 Auto Build Balance Model: Mode A (fixed territory count) vs Mode B (fixed workload target, two sub-variants: closest-to / closest-to-without-exceeding); workload formula with visit frequency multiplier; full travel time algorithm documented (quadtree + kd-tree + empirical log-scale speed model from existing Designer codebase); dwell time resolution order; visit frequency semantics (scales both dwell and travel time per cycle); bias defaults (100-0 when no metric named, 50-50 when metric named without bias); multi-metric explicitly prohibited; agent UX guidance for surfacing defaults
- Updated terminology table: Workload, Balance Bias, Dwell Time definitions revised; added Visit Frequency, Auto Build Mode A, Auto Build Mode B
- `SCENARIOS.md` v0.6.0 — added Auto Build intent translation reference table (5 canonical samples mapping natural-language requests to tool contract parameters); resolved workload block optional/default question; added visit frequency open question; annotated resolved questions

### Changed (2026-05-11) — v0.11.0 (CONSTITUTION) / v0.5.0 (SCENARIOS)
- `CONSTITUTION.md` v0.11.0 — added Workload definition to terminology table; added Section 2.10 Auto Build Balance Model capturing: workload as primary balance objective, statistical travel time estimation (±10–20% vs routed itinerary), dwell time resolution order, single optional secondary metric with bias weighting, and explicit constraint against multi-metric balancing
- `SCENARIOS.md` v0.5.0 — rewrote Scenario 003 to reflect correct Auto Build balance model: workload always included, dwell time defaulted when not in account data, one optional secondary metric with `workload_bias` / `metric_bias`, metric tension explained as expected product behavior, comparative HTML grid + map as dual output modes

### Changed (2026-05-11) — v0.4.0 (SCENARIOS)
- `SCENARIOS.md` v0.4.0 — refined Scenario 003: renamed `geocode_accounts` → `ingest_accounts` (selective geocoding only for rows missing valid coordinates); all account columns pass through as point layer properties; `balance_column` is a single named column aggregated from the point layer; multi-metric balancing explicitly out of scope for v1; two comparison output modes (styled HTML grid + interactive map with TAL switcher)

### Changed (2026-05-11) — v0.3.0 (SCENARIOS) draft
- Added `SDLC.md` to define repository documentation ownership boundaries and prevent redundancy across README, Vision, Constitution, Scenarios, Functional Spec, Technical Spec, Map Component, Design, Analysis Design, and Changelog
- `MAP_COMPONENT.md` v0.3.0 — added live Agent/MCP communication model for Monica's map-selection workflow: short-lived map sessions, subscribable selection/state resources, committed selection events, and event-driven MV refresh
- `README.md` / `VISION.md` — documented MCP Resource Subscriptions as the bridge from Map Component selection commits to agent notifications, while preserving agent-owned TS storage and EZT MCP's durably stateless posture
- Added `SCENARIOS.md` with Scenario 001: Monica selects ZIPs along a territory boundary, reviews selection impact, and realigns them from T1 to T2
- Expanded `SCENARIOS.md` with Scenario 002: Monica emails a temporary read-only latest East Coast TS/Map Component link to her boss
- Clarified sharing lanes in `README.md`: read-only Map Component for quick review, Power BI for formal executive reporting, and GeoJSON/table exports for interoperability
- Added working notes in `tmp/mv-agent-mcp-selection-workflow-2026-05-11.md` covering candidate `map_session_create`, selection resource payloads, scoped Analyze, Realign refresh, and open decisions

### Changed (2026-05-08) — v0.10.0
- `VISION.md` / `CONSTITUTION.md` v0.10.0 — aligned canonical part-layer schema name with staging PostgreSQL/PostGIS: `geo` instead of `shared_geo`
- Staging database `easyterritory` already contains `geo.us_postal`, `geo.us_postal_points`, `geo.us_county`, and `geo.ca_postal` with GiST geometry indexes

### Changed (2026-05-08) — v0.9.0
- `VISION.md` / `CONSTITUTION.md` v0.9.0 — removed Nominatim from the v1 geocoding architecture
- Geocoder provider hierarchy is now TomTom Level 1 → Azure Maps fallback
- Resource Server scope is now canonical `geo` part layers, `geocode_cache`, and spatial helper functions; it no longer includes Nominatim/geocoder reference data for v1
- PMTiles basemap pipeline remains separate from PostgreSQL and is now described as independent of geocoding rather than sharing an OSM source with Nominatim
- `README.md` / `MAP_COMPONENT.md` — aligned current-state docs with the TomTom/Azure Maps geocoding posture

### Changed (2026-05-08) — v0.8.0
- `VISION.md` / `CONSTITUTION.md` v0.8.0 — codified PMTiles basemap/part-layer architecture: same OSM source extract, separate derived outputs for Nominatim/geocoding and vector basemap PMTiles
- Clarified that Resource Server PostgreSQL/PostGIS holds Nominatim/geocoder data, `geocode_cache`, canonical `geo` part layers, and spatial helper functions — not basemap PMTiles
- Clarified that vector basemap PMTiles and part-layer PMTiles are static browser-delivery artifacts hosted from blob/object storage with HTTP Range Request support
- Clarified that curated part layers are canonical in PostGIS and exported to PMTiles for Map Component rendering/selection, while customer TS GeoJSON remains the active solution artifact and is not baked into PMTiles for v1
- `README.md` / `MAP_COMPONENT.md` — aligned overview and component notes with the PMTiles/object-storage split

### Changed (2026-05-07) — v0.7.0
- `VISION.md` / `CONSTITUTION.md` v0.7.0 — TAL cardinality changed from **0-1** to **0-N**: a TS now supports multiple Territory Alignment Layers coexisting in the same file
- Each TAL now carries a stable `tal_id` and a human-readable `label` (e.g., "By Revenue Q1", "By Headcount")
- Added `active_tal_id` top-level field to TS: identifies which TAL the Map Component renders by default; agent sets/updates this as the user switches between alignments
- Build tools (Direct Build, Account Build, Auto Build) always **append** a new TAL — never replace or modify existing TALs. The agent removes unwanted TALs after the user decides which alignment to keep.
- Realign now requires a `tal_id` parameter to identify which TAL to modify; all other TALs in the TS are untouched
- Analyze now accepts an optional `tal_ids` list; when multiple TALs are supplied, output includes a cross-TAL comparison section (head-to-head balance scores, metric distribution differences, recommendation)
- Updated TS canonical format example to show two TALs (`tal_revenue`, `tal_headcount`) with `active_tal_id`, per-TAL `label`, and per-TAL presentation metadata
- Added `VISION.md` **Comparative Territory Analysis** section with a concrete Monica workflow end-to-end
- Updated TS key rules to document the append-only build contract and the agent's responsibility for TAL removal
- Updated `CONSTITUTION.md` §4.2 (TAL section), §4.5 (layer cardinality), §4.6 (TS in/out), and terminology table accordingly

### Changed (2026-05-06) — v0.6.0
- `VISION.md` v0.6.0 — revised TS model: TS is the only geometry-bearing file format; supports 0-N point location layers and 0-1 optional territory alignment layer (TAL); Geocode Address now returns a TS with point layer and no TAL
- `VISION.md` v0.6.0 — introduced EZT MCP Resource Server: PostgreSQL/PostGIS for part geometry layers, self-hosted Nominatim + US reference datasets, geocode cache, and spatial compute support
- `VISION.md` v0.6.0 — clarified Auto Build requires/records a named part layer and preserves incoming TS point layers
- `VISION.md` v0.6.0 — added upper-management sharing model: read-only map view, Power BI-friendly projections/exports, and narrative executive summaries while preserving agent-owned TS storage
- `CONSTITUTION.md` v0.6.0 — codified Resource Server, self-hosted Nominatim-first geocoding, TS/TAL layer cardinality, and sharing-without-system-of-record rule
- `README.md` — updated summary to match v0.6.0 TS, Resource Server, geocoding, Auto Build, Analyze, and sharing model
- `VISION.md` v0.6.0 — elevated TS sharing to a flagship feature and defined unified map-component modes (`view`, `select`, future `edit`) so read-only sharing and assisted selection use the same component
- `VISION.md` v0.6.0 — revised Auto Build to take a TS as input and return an augmented TS, preserving the TS-in/TS-out workflow
- `MAP_COMPONENT.md` v0.2.0 — expanded from Map Widget stub to unified Map Component for read-only sharing and spatial selection
- `VISION.md` / `CONSTITUTION.md` / `README.md` — added Analysis Presentation Guidance as first-class product surface: Analyze returns JSON facts, while MCP resources/prompts or `ANALYSIS_DESIGN.md` guide agents in producing polished operator insight
- `VISION.md` / `CONSTITUTION.md` / `README.md` — added TS identity metadata and short-lived TS cache handles; clarified product/security language from “does not store customer data” to “does not persist customer data as system of record”
- `VISION.md` / `CONSTITUTION.md` / `MAP_COMPONENT.md` / `README.md` — added map styling model: optional TS presentation metadata, EZT MCP style templates, named views, simple classification, legends, and bounded v1 symbology scope
- Added `DESIGN.md` scaffold and documented it as the repo-level EasyTerritory design-system file for AI coding agents, derived from Benton's EZT Designer V2 visual language

### Changed (2026-05-05) — v0.5.0
- `VISION.md` v0.5.0 — strengthened agent-owns-storage posture throughout: "What Agents Can Do" now explicitly calls out agent responsibility for pulling account data from source systems and persisting TS files; TS canonical format key rules now state agent ownership explicitly; Infrastructure Model updated to describe agent custodian role; "What This Is Not" adds two new bullets: not a data store, not a proprietary format
- `VISION.md` v0.5.0 — TS is now explicitly described as valid GeoJSON (RFC 7946 FeatureCollection); EZT MCP conventions live in standard `properties` fields; no SDK required to read a TS
- `CONSTITUTION.md` v0.5.0 — §2.2 expanded: per-request statelessness described from agent perspective (TS in → compute → TS out); agent responsibility for source system data pull made explicit; §2.5 rewritten to lead with "TS is standard GeoJSON" and cite RFC 7946

### Changed (2026-05-05) — v0.4.0
- `VISION.md` v0.4.0 — redesigned canonical TS format to use a top-level envelope with `territories` + `layers[]` (N ≥ 0 point layers, first-class); `metric_fields` declared per layer; Analyze now takes only a TS (no separate account input); updated "What Agents Can Do" and "What This Is Not" to reflect map widget; updated Lifecycle section to reference MAP_COMPONENT.md
- `MAP_COMPONENT.md` v0.1.0 — new stub document: role (spatial I/O device), interaction model (TS in → part_ids[] out), selection UX primitives, embedding targets (OpenClaw Canvas primary, Teams meeting app v2), technology candidates (MapLibre + PMTiles), open questions

### Changed (2026-05-05) — v0.3.0
- `VISION.md` v0.3.0 — expanded MVP tool set: added Account Build (accounts with grouping attribute → territory solution, with internal Repair); added Realign (directed part moves on an existing territory solution); added Internal Operations section documenting Repair as a shared private pipeline step; clarified Direct Build includes internal Repair; updated "What This Is Not" to reflect modify capability
- `CONSTITUTION.md` v0.3.0 — renamed §2.6 to "Dissolve and Repair Are Internal Operations"; added Repair to territory/ module; added `Grouping Attribute` and `Realignment Instructions` to terminology table; added `repair` to territory pipeline module comment
- `README.md` — updated MVP tool list to include Account Build and Realign

### Changed (2026-05-04)
- `VISION.md` v0.2.0 — locked MVP tool set (Geocode, Direct Build, Auto Build, Analyze); clarified GeoJSON-as-universal-wire-format; defined Part/Territory/Territory Solution terminology; documented EasyTerritory-hosted infrastructure model (no customer state in EZT MCP); added canonical TS format example
- `CONSTITUTION.md` v0.2.0 — removed separate geocoder microservice (geocoding is internal to MCP); removed per-customer schema model (Postgres holds shared reference data only); added GeoJSON wire format non-negotiable; added dissolve-is-internal non-negotiable; clarified no-customer-data-persisted rule; updated terminology table
- `README.md` — updated to reflect current architecture and MVP tool set

### Added (2026-04-24)
- `CONSTITUTION.md` v0.1.0 — initial architecture, security, stack, and convention non-negotiables
- `VISION.md` v0.1.0 — initial product intent and founding capability definition

---

*Project is pre-implementation. Changelog entries will accumulate as lifecycle phases complete.*
