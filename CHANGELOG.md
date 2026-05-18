# CHANGELOG

All notable changes to EZT MCP are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Changed (2026-05-18) — cooperative job cancellation + MC cancel UX
- Promoted queued-job cancellation to a first-class cooperative outcome: Direct Build now publishes `cancelled` MC progress events, returns `JOB_CANCELLED`, and preserves terminal `cancelled` status instead of overwriting it as `failed`.
- Added cancellation checkpoints before/after expensive Direct Build stages and chunked large part-geometry fetches so large requests can observe cancellation between chunks.
- Added pending job references to MC render payloads plus a session-token-scoped browser cancel route and Cancel button in the progress overlay.
- Hardened in-memory and Postgres job repositories so terminal jobs cannot be failed again after cancellation.

### Changed (2026-05-18) — basemap visual tuning
- Reduced visual dominance of non-major roads by fading minor-road color, width, opacity, and raising the minor-road min zoom to z10. Restored PMTiles ZIP/part-layer boundary strokes to the stronger selection-friendly style. Verified basemap tile attributes: many visually local streets are classified as `major_road` with `kind_detail=secondary|tertiary`, so those secondary/tertiary road details are now styled thinner and more faded while highways/primary roads stay prominent.

### Added (2026-05-18) — part-layer click selection MVP
- Added Map Component select-mode click behavior for active PMTiles part layers: clicking inside a ZIP/part toggles its `part_id` via a transparent polygon hit layer, selected parts are highlighted, the panel selected count updates, and Commit/Clear controls manage the selected IDs. Enter remains a keyboard shortcut for commit.
- Hardened selection commits so browser payloads include `part_layer` plus de-duplicated `part_ids`, and mismatched commits are rejected when they do not match the active map part layer or first-class selection task.

### Added (2026-05-18) — production US ZIP PMTiles builder
- Added `scripts/build_part_layer_pmtiles_tippecanoe.py`, the preferred operational builder for z9+ part-layer overlays. It exports canonical PostGIS part geometry to GeoJSONSeq, runs `tippecanoe`, converts MBTiles to PMTiles, and verifies the archive.
- Built and deployed a `us_zips.pmtiles` z5–z12 archive on `expertpack.ai` from 33,715 canonical ZIP features. The deployed PMTiles is 116,524,452 bytes, serves HTTP Range requests, and replaced the earlier z5–z8 proof artifact.
- Installed Ubuntu `tippecanoe` package on the live ExpertPack droplet for operational tile builds.

### Added (2026-05-18) — point-layer range-class visual QA demo
- Added `scripts/create_point_range_demo.py`, a reusable live demo/smoke helper that posts a synthetic TS with 5 SE territories and hundreds of customer point locations to `get-map-visualization`.
- Added `examples/point_range_demo.summary.json` to record the first Brian-reviewed point-layer range-class demo session and follow-up UI refinement notes.
- The demo exercises numeric range classification over `annual_revenue_m`, class visibility rows in the Layer-Legend, point popups/labels metadata, and the `us_zips` part overlay in the same MC session.

### Added (2026-05-18) — Map Component Layer-Legend and point-layer rendering
- Added MC render-payload support for TS point layers: `point_layers` metadata summaries and `point_geojson` features now flow to the browser alongside active/reference TAL GeoJSON.
- Replaced the simple legend with an integrated Layer-Legend UI for active territories, reference alignments, point layers, and part overlays, including visibility toggles, swatches, counts, filter hints, and point-class sub-row toggles.
- Added headless point-layer styling/filter/classification rendering in the browser from TS presentation metadata: simple predicates (`eq`, `neq`, `in`, `nin`, `lt`, `lte`, `gt`, `gte`, `between`), categorical classes, and numeric break classes.
- Added a custom-content block inside the MC panel so agent-authored narrative/summary content can coexist with the Layer-Legend without becoming a symbology editor.

### Changed (2026-05-18) — migration 003 landed; compatibility fallback removed
- Confirmed `migrations/003_job_payloads_limits.sql` applied to staging DB by Matt Root (all 5 schema capability checks returned `true`).
- Removed pre-migration compatibility fallback from `ezt_mcp/db/jobs.py`: deleted `_detect_schema_capabilities`, `schema_capabilities()`, `_schema_capabilities_for_conn()`, the `_schema_capabilities` cache field, and all pre-migration branch paths in `submit`, `claim_next`, and `cleanup_expired`.
- Hardened `transient.job_payloads` + attempt/backoff path is now the only implementation.
- 115 tests pass; Direct Build smoke confirmed `completed` after deploy.

### Added (2026-05-17) — US ZIP PMTiles part overlay
- Added session-scoped Map Component part-layer metadata, a US ZIP PMTiles manifest, browser overlay control, and MapLibre PMTiles layers for mutually-exclusive part overlays.
- Added `scripts/build_part_layer_pmtiles.py` to generate `us_zips.pmtiles` from canonical PostGIS `geo.us_postal` geometry.

### Fixed (2026-05-17) — Map leaf label priority
- Sorted active Map Component render features and added label priority metadata so leaf territory labels render ahead of rollup labels when their polygons overlap.

### Changed (2026-05-17) — Repair policy skeleton
- Added a no-op territory repair pipeline seam with `RepairPolicy`, `RepairSummary`, and `RepairResult`, wiring Direct Build `repair_summary` through the new module instead of hardcoded placeholders.

### Changed (2026-05-17) — Direct Build smoke automation
- Added `scripts/smoke_direct_build.py` to submit a tiny live queued Direct Build, poll completion, verify `geometry_summary`, TAL metadata, feature geometry/types/labels, and optionally create/verify a Map Component URL/render payload.

### Changed (2026-05-16) — Direct Build live geometry and Map Component render fix
- Added reusable synthetic geometry fixtures for Direct Build/dissolve tests plus a `SyntheticPartsRepository` test double.
- Added `DissolvedHierarchy.bbox` and `DissolvedHierarchy.summary()`; Direct Build completed results now include `geometry_summary`, and TAL metadata includes `geometry_backend` plus `bbox`.
- Updated Direct Build schemas/examples and unit coverage for geometry summary, flat/hierarchical bbox, and shared synthetic fixtures.
- Deployed current main to `https://expertpack.ai/mcp/` and verified live Direct Build against real PostGIS `us_zips` completed with leaf + rollup `MultiPolygon` output, `geometry_summary`, and Map Component URL creation.
- Fixed Map Component CSS theme blocks missing closing braces, which prevented full-screen map layout from applying; redeployed and verified Brian could load the map successfully.
- Updated SDLC next-phase guidance to require deploy smokes for CSS/render-payload paths and to convert the manual Direct Build smoke into a reusable script.

### Changed (2026-05-16) — scalability, TAL IDs, and queue recovery
- Added temporary pre-migration compatibility mode so staging can deploy/test queue hardening before migration 003 lands; when `transient.job_payloads` / attempt columns are absent, queued payloads fall back to legacy `request_summary` storage and stale-running reclaim is disabled.
- Added worker-driven cleanup for expired transient job payloads/results and terminal job rows, keeping `transient.job_payloads` / `transient.job_results` bounded after migration 003 lands.
- Added `transient.job_payloads` plus job `payload_handle` metadata so full queued request payloads are stored outside `request_summary`.
- Added configurable transient job limits (`jobs.max_queued_jobs_per_customer`, `jobs.max_active_jobs_per_customer`) with `JOB_LIMIT_EXCEEDED` responses.
- Added retry hardening for stale running-job reclaim: attempt counts, max attempts, retry backoff, and `JOB_ATTEMPTS_EXHAUSTED` failure.
- Updated `SDLC.md` next-phase guidance to keep queue hardening/operator status in the correct owning docs and to treat migration `003_job_payloads_limits.sql` as the live deploy gate.
- Extended `scripts/zip_scalability.py` with `--state ALL` national sampling for larger real ZIP benchmarks.
- Verified national ZIP scalability on staging: 5k / 50 territories in ~5.65s, 10k / 100 in ~13.77s, 20k / 200 in ~27.65s, and full 33,715 ZIPs / 337 in ~50.39s with no warnings.
- Added caller-supplied Direct Build TAL IDs via `tal_id` / `requested_tal_id`, including format validation and collision rejection against existing TS TAL IDs.
- Added stale running-job lease reclamation so expired `running` jobs can be reclaimed by a later worker instead of remaining stuck after worker death.

### Changed (2026-05-15) — create territory, queued worker, progress, and scalability
- Implemented `create_territory_from_parts` as a real queued Direct Build-backed mutation path, including `POST /create-territory-from-parts` for HTTP smoke/dev use.
- Added persisted queued job payloads plus a startup `JobWorker` that claims queued `direct_build` / `create_territory_from_parts` jobs from `transient.jobs` instead of running per-request compute via process-local task submission.
- Wired Direct Build worker phases to publish best-effort MC progress events when `map_session_id` is supplied.
- Added `scripts/zip_scalability.py` for read-only real ZIP scalability benchmarking against staging PostGIS.
- Updated Functional/Technical/SDLC docs for the queued worker/create-territory implementation and current hardening gaps.
- Verified real FL ZIP benchmark locally and after deploy; deployed run: 1000 ZIPs / 20 territories fetched in ~0.822s, built in ~0.828s, total ~1.650s.

### Changed (2026-05-15) — MC themes, progress, and durable-session deployment path
- Added MC light/dark theme support driven by `presentation.style_overrides.theme`; dark remains the default for development/testing unless explicitly requested.
- Added `set_map_progress` plus `POST /set-map-progress` to push best-effort `progress` SSE events to open MC sessions, rendering a bottom-center progress overlay with message, optional percent bar, and running/done/error/idle states.
- Added Postgres-backed `AsyncpgMapSessionStore` and `scripts/migrate_map_sessions.py` for `transient.map_sessions`; service uses it automatically when the table exists and falls back to in-memory sessions otherwise.
- Deployed to `https://expertpack.ai/mcp/` and verified health, dark MC render payload, progress events, and restart-surviving Postgres-backed durable map sessions after the DB owner applied the migration.

### Changed (2026-05-14) — Map Component customer labels and i18n
- Replaced visible MC chrome text that said “TAL” with customer-facing “alignment” labels while preserving internal `tal_*` API and payload field names.
- Added resolved `presentation.chrome_labels` defaults/overrides so MC chrome labels can be internationalized via presentation metadata or request-time overrides instead of hardcoded viewer strings.
- Documented that MC product chrome must use customer-appropriate, localizable labels and avoid exposing internal acronyms.

### Changed (2026-05-14) — Direct Build dissolve performance and tuning
- Optimized the Shapely dissolve backend to avoid re-repairing already-normalized input geometries; final union output is still repaired/validated.
- Added optional Benton-style two-pass spatial partitioning to the Shapely backend with configurable `partition_threshold`, `target_parts_per_cluster`, and `max_clusters`; local benchmarks showed direct GEOS `unary_union` is faster through at least 5k synthetic parts, so the default threshold is intentionally high (`10000`) while keeping the partitioned path available for pathological real-world cases.
- Added config-driven dissolve simplification controls (`simplify_tolerance`, `overview_simplify_tolerance`) plus environment overrides.
- Documented that PostGIS backend selection is tabled until real dev data justifies it, and sliver buffer cleanup should only be added behind an explicit option if visible artifacts appear.
- Expanded unit coverage for fast-path dissolve, empty geometry errors, partitioned output equivalence, and config parsing.

### Changed (2026-05-14) — Map Component active TAL switching
- Added direct Map Component switching between TALs in a multi-TAL TS: one active TAL renders normally while sibling TALs remain visible as dimmed reference context.
- `get_map_visualization` render payload now includes active/reference GeoJSON separation plus `available_tals`; browser sessions retain the source TS/presentation context so the active TAL can be rebuilt server-side without a new agent tool call.
- Added browser-safe active-TAL session update endpoint and extended `set_map_state` to accept `active_tal_id`.
- Added a prominent floating active-alignment selector in the MC, including runtime DOM fallback for rapid-deploy HTML/JS asset skew and explicit dropdown contrast styling.
- Added unit/route coverage for active TAL switching and updated Functional/Technical/Map Component docs for the v1 behavior.

### Changed (2026-05-13) — map visualization as early v1 capability
- Renamed the public map-session tool contract from `map_session_create` to `get_map_visualization` to reflect user/agent intent: get a browser-safe Map Component visualization for a TS/TAL
- Added S004 / MC-000 visual verification scenarios: Brian/developers need read-only MC visualization early to validate Direct Build, Realign, Auto Build, Analyze, styling, labels, rollups, and repair effects
- Updated Technical Spec implementation sequence to build a minimal read-only `get_map_visualization` loop before deeper compute/job infrastructure; select-mode resources and live refresh can layer on later
- Renamed schema/example files to `get_map_visualization.schema.json` and `get_map_visualization.*.json`; existing map-session resources remain internal/session concepts

### Changed (2026-05-13) — async jobs and multi-tenant concurrency
- `CONSTITUTION.md` v0.18.0 — locked all v1 customer-data compute tools (`geocode_address`, `ingest_accounts`, `direct_build`, `account_build`, `auto_build`, `realign`, `analyze`) as asynchronous job submissions; added authoritative pull progress/result with opportunistic MCP push progress; elevated multi-tenant job/cache/session isolation and fair concurrency controls to non-negotiables
- `FUNCTIONAL_SPEC.md` v0.2.0 — added async job contract, job result semantics, customer-scoped polling/cancellation behavior, and clarified initial tool calls return job references instead of final compute results
- `TECHNICAL_SPEC.md` v0.2.0 — added transient job/progress/result storage, submission vs worker execution pipeline, progress phases, cooperative cancellation, workload-specific execution pools, and per-customer/global fairness controls
- Added `schemas/job.schema.json`, a Direct Build submission response example, and a running job status resource example; existing tool response schemas now distinguish initial submission response from completed job result payloads

### Changed (2026-05-12) — deploy target and EP MCP lineage clarified
- Clarified that EZT MCP deploy/test uses the ExpertPack droplet `165.245.136.51` / `expertpack.ai`, reusing the `/mcp` reverse-proxy path unless a separate path is intentionally introduced later
- Clarified implementation lineage: EZT MCP is forked/derived from EP MCP and should reuse the proven FastMCP/Starlette/service/deploy shape

### Added (2026-05-12) — part-layer discovery resources
- Added Functional Spec resources `ezt://part-layers` and `ezt://part-layers/{part_layer}` so agents can discover available canonical part layers before calling build/realign/analyze tools
- Expanded Technical Spec part-layer metadata and resource implementation notes, including safe public fields, capability flags, and internal metadata redaction
- Added first implementation slice for part-layer discovery: package scaffold, safe public metadata model, PostGIS-backed repository stub, resource helper functions, schema/examples, and unit tests

### Added (2026-05-12) — Technical Spec implementation baseline
- Added `TECHNICAL_SPEC.md` v0.1.0 covering runtime architecture, module boundaries, PostGIS/transient storage design, TS internal representation, common tool pipeline, territory computation pipeline, per-tool implementation designs, map sessions, security, observability, performance limits, testing strategy, deployment, and implementation sequence
- Updated `README.md` lifecycle/status links and `FUNCTIONAL_SPEC.md` routing language to include the Technical Spec

### Added (2026-05-12) — schema examples and validation
- Added `schemas/examples/` test vectors for `direct_build` flat/hierarchical cases, `auto_build` Mode A/Mode B/Scoped Split, `realign`, `analyze`, and `map_session_create`
- Added `schemas/validate_examples.py` to validate each example against its tool contract request/response definition
- Tightened schema composition discovered by examples: `tsOutputRef` now permits tool-specific result fields, and `auto_build.objective.metric` is a single non-empty string definition

### Changed (2026-05-12) — DESIGN.md v0.2.0 and cross-links
- Replaced the `DESIGN.md` scaffold with Benton's extracted EZT Designer V2 design-system contract: populated tokens, map-specific styling, hard rules, chrome variants, source surfaces, references, and open design questions
- Tightened `README.md`, `FUNCTIONAL_SPEC.md`, `MAP_COMPONENT.md`, and `SDLC.md` cross-links so implementation agents treat `DESIGN.md` as the canonical visual source for the Map Component

### Added (2026-05-12) — realign, analyze, map_session_create schemas
- Added `schemas/realign.schema.json` — directed part-move operations, changed-territory summary, repair side effects, and optional MC session refresh notification
- Added `schemas/analyze.schema.json` — TAL analysis, per-territory metric distributions, balance scores, outliers, scoped aggregates (map selection), cross-TAL comparison, hypothetical move impact, caveats, and presentation guidance URI
- Added `schemas/map_session_create.schema.json` — session mode (view/select), presentation context, interaction flags, expiry, browser-safe `map_url`, selection and state resource URIs, and active TAL summary
- Updated `schemas/README.md` to list all six schemas

### Added (2026-05-11) — initial schemas
- Added `schemas/` with draft JSON Schema 2020-12 external contracts: common envelope/error types, TS references/identity, `direct_build`, and `auto_build` including Scoped Split
- Linked `FUNCTIONAL_SPEC.md` to the new schema drafts

### Changed (2026-05-11) — v0.1.1 (FUNCTIONAL_SPEC) / v0.9.1 (SCENARIOS)
- Resolved v1 open questions: territory split is v1 via Auto Build Scoped Split (not Realign); TS cache is implicit (no public `ts_cache_put` tool); `map_session_create` is v1 with browser URL/OpenClaw Canvas first; schemas start before implementation; Power BI/export contracts are post-MVP; Point Location Update is post-MVP
- `FUNCTIONAL_SPEC.md` v0.1.1 — updated v1 public tool surface, added Auto Build Scoped Split behavior, replaced open questions with resolved v1 scope decisions, and moved cache to implicit behavior
- `SCENARIOS.md` v0.9.1 — replaced remaining open-question notes with resolved decisions

### Added (2026-05-11) — v0.1.0 (FUNCTIONAL_SPEC)
- Added `FUNCTIONAL_SPEC.md` v0.1.0 — initial external behavior contract covering common TS/handle conventions, structured errors, v1 draft MCP tools (`geocode_address`, `ingest_accounts`, `direct_build`, `account_build`, `auto_build`, `realign`, `analyze`, `map_session_create`, `ts_cache_put`), map-session resources, guidance resources, open design questions, and scenario coverage matrix

### Changed (2026-05-11) — v0.9.0 (SCENARIOS)
- `SCENARIOS.md` v0.9.0 — refactored from detailed scenario specs into a lean scenario registry: terse numbered narrative steps only, no JSON/tool contracts/subsections; added coverage for Geocode Address, Ingest Accounts, Direct Build, Account Build, Realign, Analyze, Map Component/sharing, TS cache/identity, and future Point Location Update scenarios

### Changed (2026-05-11) — v0.16.0 (CONSTITUTION) / v0.8.0 (SCENARIOS)
- `SCENARIOS.md` v0.8.0 — added Auto Build Scenario Suite (AB-001 through AB-016) as a testbed covering every Auto Build contract variation: pure workload (Mode A), session default persistence, workload+metric with 50-50 default, explicit bias, pure metric (workload_bias=0), synthetic account count, Mode B closest-to and not-to-exceed, Mode B+metric, visit frequency column, raw text visit frequency normalization (agent responsibility), build-time dwell override, per-account dwell column, multi-metric rejection (agent explains), Mode A/B mutual exclusion

### Changed (2026-05-11) — v0.16.0 (CONSTITUTION) / v0.7.0 (SCENARIOS)
- `SCENARIOS.md` v0.7.0 — added Key Terms table at top of document defining TS, TAL, MC, MV, MCP, EP, T, P on first use; pointer to CONSTITUTION.md §4.1 for full definitions
- `CONSTITUTION.md` v0.16.0 — added key abbreviations inline at top of document (TS, TAL, MC, MCP, EP, T, P) with pointer to §4.1
- `VISION.md` — added key abbreviations inline at top of document with pointer to CONSTITUTION.md §4.1

### Changed (2026-05-11) — v0.15.0 (CONSTITUTION) / v0.6.3 (SCENARIOS)
- `CONSTITUTION.md` v0.15.0 — locked `active_tal_id` behavior: Auto Build always sets it to the newly appended TAL; agent may override explicitly
- `SCENARIOS.md` v0.6.3 — marked `active_tal_id` open question as resolved

### Changed (2026-05-11) — v0.14.0 (CONSTITUTION) / v0.6.2 (SCENARIOS)
- `CONSTITUTION.md` v0.14.0 — expanded dwell time resolution: session default (agent-owned, persists across builds), build-time override, agent UX guidance (scan columns for dwell-time candidates, ask Monica, offer to persist as default); agent is responsible for scrubbing visit frequency raw formats (decimal, inverse-weeks, free text) into normalized `visits_per_cycle` float before passing to EZT MCP; account count synthetic metric supported natively (no column required); max batch size for `ingest_accounts` TBD (most customers 10K, some 100K+)
- `SCENARIOS.md` v0.6.2 — marked dwell time and visit frequency open questions as resolved; annotated batch size and `active_tal_id` as TBD

### Changed (2026-05-11) — v0.13.0 (CONSTITUTION) / v0.6.1 (SCENARIOS)
- `CONSTITUTION.md` v0.13.0 — locked visit frequency as an account-data attribute only (never a build-time parameter); optional, ingested via `ingest_accounts` as a point layer property; null/absent rows default to frequency = 1; cycle-unit consistency requirement clarified
- `SCENARIOS.md` v0.6.1 — marked visit frequency open question as resolved

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
