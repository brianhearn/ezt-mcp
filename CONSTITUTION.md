# CONSTITUTION.md — EZT MCP Non-Negotiables

**Version:** 0.16.0
**Date:** 2026-05-11
**Status:** Draft

These are the architectural, security, stack, and convention decisions that are locked for the life of the project. Deviations require explicit revision of this document with justification. All downstream specs and implementation must conform.

**Key abbreviations used throughout:** **TS** = Territory Solution (the primary GeoJSON artifact), **TAL** = Territory Alignment Layer (one named territory arrangement within a TS), **MC** = Map Component (the browser-based map surface), **MCP** = Model Context Protocol, **EP** = ExpertPack (the domain knowledge layer), **T** = Territory, **P** = Part (the atomic geographic unit). Full definitions in §4.1 (Terminology).

---

## 1. Stack

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.12+ | No exceptions |
| MCP framework | FastMCP (official MCP SDK) | Inherited from ep-mcp |
| Web layer | Starlette + Uvicorn | Inherited from ep-mcp |
| CLI | Click | Inherited from ep-mcp |
| Resource Server | PostgreSQL + PostGIS | Part layers, geocode cache, spatial compute support — shared resources only |
| Map renderer | MapLibre GL JS | Primary Map Component renderer candidate |
| Tile delivery | PMTiles | Static vector basemap and part-layer delivery artifacts served from object/blob storage, not PostgreSQL |
| Spatial / geo library | GeoPandas + Shapely | Territory computation pipeline (dissolve, partition, zone, realign) |
| Containers | Azure Container Apps | Stateless MCP instances |
| Secrets (production) | Azure Key Vault | No plaintext credentials in config files or env vars in production |
| Infra-as-code | Delegated to Matt Root | Not defined here |
| Testing | TBD | To be defined before Implementation phase |

---

## 2. Architecture Non-Negotiables

### 2.1 Stateless MCP Tier
The EZT MCP application container is **durably stateless**. It holds no persistent customer data, no durable territory solutions, and no mutable customer state that must survive restart. The Resource Server holds only shared reference data and shared spatial infrastructure (part layers, geocode cache, spatial indexes/functions). Container restarts and horizontal scaling are transparent to clients except for optional short-lived cache misses.

### 2.2 No Per-Customer State in EZT MCP
EZT MCP does not persist territory solutions, account data, or any customer-specific data as a system of record. Every tool call supports the fully stateless path: the agent passes the current TS in, EZT MCP computes, the updated TS comes back out. For efficiency, the agent may use short-lived cache handles instead of repeatedly transmitting the same multi-MB TS. The agent is responsible for persisting outputs and for retrieving account data from the customer's source systems (CRM, spreadsheets, databases) before embedding it as a point layer.

This is a deliberate design choice — it minimizes data isolation complexity, reduces GDPR surface area, keeps the Resource Server footprint bounded, and keeps EZT MCP horizontally scalable. Short-lived cache entries are allowed only as a transport optimization and must not become durable customer storage.

### 2.3 Resource Server — Shared Spatial Infrastructure Only
A single EasyTerritory-hosted Resource Server, implemented as PostgreSQL/PostGIS, serves all customers. It contains:
- `geo` schema — part layer polygons (US ZIPs, US counties, US states, Canadian FSAs, etc.). Read-only from the application.
- `geocode_cache` schema — address → lat/lon cache. Shared across all customers; contains no customer-identifying data.
- Spatial helper functions/indexes used by the territory computation pipeline when work is better performed in PostGIS than in the application container.

There are no per-customer schemas. The Resource Server is shared infrastructure, not customer storage. The application user has the minimum privileges required to read shared spatial resources, execute approved spatial helper functions, and read/write the geocode cache.

Basemap PMTiles do not live in the Resource Server. OSM-derived basemap generation is a separate cartographic build pipeline and is not coupled to the geocoder.

### 2.4 Geocoding — Internal to MCP
Geocoding is handled directly by EZT MCP (no separate geocoder microservice). Provider selection, tier routing, fallback, and cache lookup/write are all implemented within the MCP server. Provider credentials (TomTom, Azure Maps) are sourced from Azure Key Vault at startup.

Provider hierarchy: TomTom Level 1 → Azure Maps fallback.

### 2.5 GeoJSON as the Universal Wire Format
The Territory Solution (TS) is standard GeoJSON — a `FeatureCollection` with EZT MCP conventions expressed in standard `properties` fields. It is not a proprietary format, a custom binary, or an EZT-specific file type. Any GeoJSON-aware tool or library can parse a TS without an EZT SDK.

All geometry-bearing inputs and outputs are TSes. Geocode Address returns a TS with point location features and no territory alignment layer. No other geometry format is accepted or produced. GeoJSON geometry follows RFC 7946.

The one exception: the Analyze Territory Solution tool returns structured JSON with no geometry, since analysis results are tabular. If those results need to travel with geometry, the agent can attach them back into a TS as properties or companion metadata in a later workflow.

### 2.6 Dissolve and Repair Are Internal Operations
Territory dissolution (union of geographic parts into a territory polygon) and Repair (hole-filling, contiguity restoration) are internal computation steps, not exposed MCP tools. They are implemented as shared library functions used by the build tools (Direct Build, Account Build, Auto Build) and Realign. The territory solution output always includes pre-dissolved geometry — the canonical format is self-contained and requires no separate part layer to render.

### 2.7 ExpertPack — Shared Knowledge Layer
A single shared ExpertPack backs the domain knowledge layer for all customers. All customers query the same pack. Per-customer pack overlays are not in scope for v1.

### 2.8 EasyTerritory Hosts Everything
EZT MCP infrastructure is hosted and operated by EasyTerritory. Customers are not responsible for deployment, the Resource Server, PostGIS, geocoder providers, or part layer data. Customer access is via API key only.

### 2.9 Sharing Is Flagship, But Not System of Record
EZT MCP must support executive sharing workflows as a first-class flagship capability, but it must not become the system of record for customer Territory Solutions. Sharing surfaces are read-only projections of a TS supplied by the customer's agent or storage layer. Supported sharing directions include unified map-component views, Power BI-friendly projections/exports, and narrative executive summaries generated from TS + Analyze output.

Read-only sharing and assisted map selection must use the same underlying map component with capability flags/modes, not two divergent UI implementations.

### 2.10 Auto Build Balance Model

#### Two build modes — mutually exclusive

**Mode A — Fixed territory count:** Operator specifies N territories. EZT MCP balances workload (and optional metric) across exactly N territories. Territory count is an input; workload per territory is an output.

**Mode B — Fixed workload target:** Operator specifies a target workload per territory (e.g. 40 hours per week). EZT MCP computes total workload across all accounts, derives N = total_workload ÷ target, then builds N territories minimizing deviation from the mean — not just trying to approach the target. Two sub-variants:
- **Closest to:** minimize deviation from the target across all territories
- **Closest to without exceeding:** no territory exceeds the target; minimize deviation from below

In Mode B the operator never specifies both a target AND a territory count — they are mutually exclusive. The territory count is derived. The goal is always minimum deviation across all territories (one outlier territory far from target is not acceptable).

#### Workload definition

Workload for a territory = Σ over all accounts i in the territory of: `(travel_time_i + dwell_time_i) × visit_frequency_i`

where the sum is over one visit cycle (e.g. one week). Travel time and dwell time are estimated per account (see below). Visit frequency scales both.

#### Travel time estimation

Travel time between accounts is estimated using a spatial quadtree + kd-tree model derived from the existing EZT Designer codebase (`partitioning.quadtree.ts`, `partitioning.utility.ts`). The algorithm:

1. Account point cloud is recursively partitioned into a quadtree (max depth 6, leaf threshold 16 points).
2. Within each leaf cell, a kd-tree finds the nearest-neighbor graph distance (MST approximation).
3. Inter-cell travel is estimated as centroid-to-centroid distance with latitude scale correction.
4. Distance is converted to time using an empirical log-scale speed model:
   - `speed (m/hr) = (15 × log10(clamp(dist_km, 1, 1000)) + 5) × 1609.34`
   - Short distances (~1 km) → ~5–8 mph effective speed
   - Medium distances (~10 km) → ~24 mph
   - Long distances (~100 km) → ~39 mph
   - Under 10 meters → floored at 24 km/hr
5. Duplicate locations (same coordinates, e.g. multi-rep same building) are tracked and excluded from distance computation but included in dwell-time totals.

This model reflects the empirical observation that US roads are laid down with reasonable efficiency — random points at the same straight-line distance tend to have similar transit times across large account sets. Exceptions exist (mountains, water bodies, dense urban cores). The estimate typically carries **±10–20% error** versus an actual routed itinerary. This is acceptable at the planning stage. Travel time estimation accuracy is an area for future improvement.

#### Dwell time resolution

Dwell time is resolved in this order:

1. **Per-account column** in the TS point layer (e.g. `avg_visit_duration`) — operator/agent specifies column name at build time.
2. **Session default** — a scalar average set by Monica earlier in the engagement and stored by the agent (not by EZT MCP). The agent carries this forward across TS builds and applies it whenever no per-account column is available.
3. **Build-time override** — Monica may override the session default for a specific build (e.g. "use 1 hour for this one instead of our usual 30 minutes"). Applies to that build only; does not update the session default unless Monica says so.
4. If `workload_bias = 0` (pure metric balance) → dwell time is not required and must not be requested.

**Agent UX guidance for dwell time:**
When starting a workload-based build and no dwell time column has been identified and no session default exists, the agent should:
- Scan the account column list for numeric columns that look like dwell time (e.g. names containing `dwell`, `visit_duration`, `stop_time`, `service_time`, `call_time`).
- If a candidate column is found: ask Monica whether to use it as the per-account dwell time column.
- If no candidate column is found: ask Monica for an average dwell time.
- After establishing the default: ask "Would you like me to use this going forward?" and store it as the session default if Monica agrees.

The session default is agent-owned state, not an EZT MCP concept. EZT MCP always receives a resolved dwell time value (column name or scalar) per build call — it never stores operator preferences.

#### Visit frequency

Visit frequency is always an attribute on the account/location data — it is never a build-time parameter. When present, it is a column in the TS point layer (ingested via `ingest_accounts` alongside all other account columns). Many customers do not have visit frequency data at all; it is optional.

When a visit frequency column is present and referenced, both dwell time AND estimated travel time are multiplied by the normalized visit frequency to compute per-cycle workload for that account.

**Normalization — agent responsibility:** Customer data is not consistent in how visit frequency is expressed. Common formats include:
- Decimal visits per cycle: `2.0` = twice per week, `0.5` = once every two weeks
- Weeks between visits (inverse): `"3"` = once every 3 weeks = `1/3` visits/week; `"0.5"` = twice per week
- Free text: `"twice per week"`, `"monthly"`, `"bi-weekly"`

The agent is responsible for scrubbing the raw frequency column into a normalized decimal `visits_per_cycle` float before passing it to EZT MCP. EZT MCP expects a single numeric `visits_per_cycle` value per account — it does not parse text or interpret inverse formats. The agent should surface a sample of raw values to Monica for confirmation before normalizing, especially when the format is ambiguous (e.g. `"2"` could mean twice per cycle or every 2 cycles).

Accounts without a visit frequency value (column absent, or null for a given row) default to `visits_per_cycle = 1`. The normalization cycle (weekly, monthly, etc.) must be consistent across all accounts and must match the cycle unit used in any Mode B workload target.

#### Secondary metric and bias

Workload is always the primary balance objective. The operator may optionally specify **exactly one** secondary metric column:

- `workload_bias=100` (no metric) — pure workload balance. **Default when no metric is named; no explicit bias input required.**
- `workload_bias=50, metric_bias=50` — equal importance. **Default when a metric is named but no bias is specified.**
- `workload_bias=0, metric_bias=100` — pure metric balance; dwell time not required.
- Any other split summing to 100 is valid.

**Account count as a synthetic metric** is supported natively by EZT MCP. The operator does not need a literal `account_count` column — Auto Build can use account density (1 per account, summed to part level) as the balance objective without any column reference. The agent should recognize natural-language requests like "same number of accounts" and map them to the native synthetic metric parameter.

**Multiple secondary metrics are not supported.** Competing metric tensions compound and produce poorly balanced results across all dimensions. The correct approach is to build separate single-metric TALs and compare them. This is a deliberate product constraint, not a technical limitation.

**`active_tal_id` after Auto Build:** Each Auto Build call sets `active_tal_id` to the newly appended TAL. This means the Map Component always renders the freshest alignment by default without requiring an explicit agent update. When building multiple TALs sequentially, the last build's TAL will be active on completion. The agent may override `active_tal_id` explicitly if a different TAL should be the default view.

**Agent UX guidance:** When an operator specifies a metric without a bias, the agent should surface the 50-50 default and invite adjustment before building. When workload requires dwell time and none is in the data, the agent must ask for a default before calling Auto Build. When Mode B is used, the agent should confirm the derived territory count before building.

### 2.11 Analysis Presentation Guidance Is Product Surface
Analyze Territory Solution returns structured JSON facts. EZT MCP must also provide agent-facing presentation guidance — as MCP resources/prompts and/or versioned markdown such as `ANALYSIS_DESIGN.md` — so calling agents can turn analysis JSON into clear, domain-appropriate operator insight.

This guidance is part of the product surface, not incidental documentation. It must be versioned, tested against example analysis outputs, and kept aligned with the Analysis tool schema.

### 2.12 Short-Lived TS Cache Is Allowed
TS payloads may be many MBs. EZT MCP may provide cache-check/cache-put/cache-handle behavior so agents can avoid repeatedly transmitting full TS payloads across sequential tool calls. This cache is permitted only as a TTL-bound transport optimization, not as durable storage or a customer system of record.

A cache miss must be safe and expected: the agent can always resend the full TS. Cache handles must be scoped to the customer/API key and must not be guessable.

### 2.13 TS Presentation Metadata and Styling
The Map Component must support declarative TS presentation metadata for lightweight but useful styling. Styling must travel with the TS as GeoJSON-compatible metadata and/or be resolved from versioned EZT MCP style resources/templates. The component must render the same style spec consistently in read-only `view` and assisted `select` modes.

V1 styling must stay intentionally smaller than EZT Designer: territory colors/boundaries/opacity, labels, point symbol styling, simple classification, legends, and named visualization presets. Full Designer-style symbology editing, complex filtering, clustering, hotspots, and print layouts are not required for v1 unless later specs explicitly add them.

### 2.14 DESIGN.md Product Design System
The repo must contain a `DESIGN.md` file that captures the EasyTerritory product design language for AI coding agents. `DESIGN.md` should follow the emerging AI-agent design-system pattern: YAML frontmatter for machine-readable tokens and Markdown prose for rationale, constraints, and component guidance.

EZT Designer V2 is the visual source of truth. The Map Component must use `DESIGN.md` for product chrome, controls, legends, panels, empty/loading/error states, and default visual language. TS presentation metadata remains responsible for solution-specific map symbology.

### 2.15 PMTiles Are Static Delivery Artifacts
PMTiles archives are read-only browser delivery artifacts, not authoritative operational data stores. Vector basemap PMTiles are generated from OSM-derived cartographic processing, preferably Protomaps/Planetiler-style, and hosted in blob/object storage with HTTP Range Request support. They are not stored in PostgreSQL.

Curated part layers are canonical in `geo` PostGIS tables. Part-layer PMTiles may be generated from those tables for Map Component rendering and selection hit-testing. Regenerating part-layer PMTiles is an operational build step when canonical part geometry changes.

Customer-specific TS data is not baked into PMTiles for v1. The Map Component renders agent-supplied TS GeoJSON for active territory solutions, overlaid on static basemap and part-layer PMTiles.

---

## 3. Security Non-Negotiables

### 3.1 API Keys
- Every API key is customer-scoped
- Keys are stored **hashed** (bcrypt or Argon2) — plaintext keys are never persisted
- Keys are transmitted in the `Authorization: Bearer <key>` header only — never in URLs, query parameters, or request bodies
- Keys support rotation: a new key can be issued before the old one is revoked, with a configurable grace period
- Key metadata (label, created_at, last_used_at, expires_at) is stored alongside the hash

### 3.2 Audit Log
Every MCP tool call is logged with: `customer_id`, `tool_name`, `timestamp`, `source_ip`, `success` (bool), `error_code` (if applicable). The audit log is append-only.

### 3.3 TLS
All external traffic is TLS-encrypted. No plain HTTP endpoints in any environment except local development on loopback.

### 3.4 No Credentials in Code or Config Files (Production)
In production, all secrets are sourced from Azure Key Vault. Config files may reference Key Vault secret names but never contain secret values.

### 3.5 Principle of Least Privilege
The application Resource Server user has least-privilege access only: read shared spatial resources, execute approved spatial helper functions, and read/write `geocode_cache`. No customer schemas exist. Geocoder provider credentials are loaded from Key Vault at startup and held in memory only.

### 3.6 No Customer Data Persisted
EZT MCP never writes customer territory solutions, account data, or alignment files to persistent storage as a system of record. Customer data is transient — received in the request, used for computation, optionally held in short-lived cache, returned in the response, and discarded when TTL expires or capacity requires eviction.

Short-lived cache entries are still customer data and must be treated accordingly: customer/API-key scoped, TTL-bound, size-limited, encrypted or memory-resident according to deployment policy, excluded from backups, excluded from logs, and safely evicted.

---

## 4. Data Model Non-Negotiables

### 4.1 Terminology

| Term | Definition |
|---|---|
| **Part (P)** | A single geographic unit (e.g., one ZIP code polygon). The atomic unit of territory composition. |
| **Territory (T)** | The dissolved union of one or more parts assigned to a named territory. A T is a GeoJSON Feature with dissolved MultiPolygon geometry and `part_ids` in properties. |
| **Territory Solution (TS)** | The universal EZT MCP geometry artifact — a GeoJSON FeatureCollection that may contain 0-N point location layers and 0-N territory alignment layers (TALs), plus solution-level metadata. |
| **Part Layer** | A named collection of part polygons stored on the Resource Server in `geo` (e.g., `us_zips`, `us_counties`, `ca_fsa`). |
| **Alignment File** | A customer-supplied CSV or Excel file mapping part identifiers (e.g., ZIP codes) to territory names. Input to Direct Build. |
| **Grouping Attribute** | A non-spatial attribute on an account record (e.g., sales manager name, territory name) used by Account Build to infer territory assignments. |
| **Realignment Instructions** | A set of directed part-move operations supplied to the Realign tool: move part P from territory A to territory B, or into a new territory. |
| **Point Layer** | A named collection of point features embedded in a TS (e.g., accounts, stores, service locations). A TS supports 0-N point layers. Each layer declares `metric_fields` — the attributes Analyze should aggregate. |
| **Metric Fields** | Attribute names on a point layer that carry quantitative values for analysis (e.g., `annual_revenue`, `account_count`). Declared at the layer level in the TS. |
| **Workload** | The estimated total time burden for a sales rep to service all accounts in a territory in one visit cycle. Workload = Σ (travel_time_i + dwell_time_i × visit_frequency_i) for each account i in the territory. Travel time per account is a statistical estimate derived from account coordinates (see Section 2.10). Workload is the primary balance objective in Auto Build and is always present unless the operator explicitly sets `workload_bias=0`. |
| **Balance Bias** | A weight pair `(workload_bias, metric_bias)` summing to 100 that controls the relative importance of workload vs. a secondary metric column in Auto Build. Default when a metric is named but bias is not specified: 50–50. Default when no metric is named: `workload_bias=100`. Example: `workload=0, metric=100` = pure metric balance (dwell time not required). |
| **Dwell Time** | The estimated time spent at a single account location per visit. Sourced from a per-account column in the TS point layer when available; otherwise an operator-supplied scalar default. Only required when `workload_bias > 0`. |
| **Visit Frequency** | How often each account is visited per cycle (e.g. once per week, twice per week, once per month). When present as a column in the account data, both dwell time and estimated travel time are multiplied by the visit frequency to compute per-cycle workload for that account. Accounts without a visit frequency column are assumed to have frequency = 1. |
| **Auto Build Mode A** | Fixed territory count: operator specifies N territories. EZT MCP balances workload (and optional metric) across exactly N territories. Territory count is an input. |
| **Auto Build Mode B** | Fixed workload target: operator specifies a target workload per territory (e.g. 40 hours). EZT MCP derives territory count = total_workload ÷ target, then balances across that many territories to minimize deviation from the mean. Two sub-variants: (a) minimize deviation from target, (b) minimize deviation from target without exceeding it. Mode A and Mode B are mutually exclusive inputs. |
| **Territory Alignment Layer (TAL)** | A named polygon layer inside a TS representing one territory alignment. A TS supports 0-N TALs. Each TAL has a stable `tal_id` and a human-readable `label`. Each territory feature within a TAL carries dissolved geometry and `part_ids`. |
| **Resource Server** | EasyTerritory-hosted PostgreSQL/PostGIS instance containing shared part layers, geocode cache, and approved spatial helper functions. It is not customer storage. |
| **PMTiles** | Static single-file tile archives used by the Map Component for vector basemap and part-layer delivery. PMTiles are hosted from blob/object storage with Range Request support, not stored in PostgreSQL. |
| **Analysis Presentation Guidance** | Versioned guidance exposed to agents as resources/prompts or markdown, instructing them how to present Analyze output in executive, designer, sales manager, and QA contexts. |
| **TS Identity** | Metadata carried by a TS: stable `ts_id`, current `revision`, deterministic `content_hash`, and `updated_at` timestamp. |
| **TS Handle** | Short-lived, customer-scoped, non-guessable cache reference that lets a tool call refer to a cached TS payload instead of retransmitting it. Not durable storage. |
| **Presentation Metadata** | Declarative styling and visualization metadata carried in a TS or referenced from EZT MCP style templates: visibility, colors, labels, classifications, symbols, legends, named views, and the `active_tal_id` controlling which TAL the Map Component renders by default. |
| **DESIGN.md** | Repo-level design-system file for AI coding agents, combining machine-readable design tokens with human-readable guidance derived from EZT Designer V2. |

Use these terms consistently in all tool names, resource names, API surface, documentation, and the ExpertPack.

### 4.2 Territory Alignment Layers Are Optional, Multiple, and Dissolved
A TS supports zero or more Territory Alignment Layers (TALs). Each TAL is independently identified by a stable `tal_id` and carries a human-readable `label` (e.g., "By Revenue Q1", "By Headcount"). When a TAL is present, each Territory feature within it carries dissolved polygon geometry — the union of all its constituent parts. A TS is self-contained: `part_ids` records composition and `part_layer` identifies the atomic geography used to construct each TAL, but the renderable geometry is pre-computed and embedded.

Multiple TALs coexisting in the same TS are the foundation of comparative territory analysis. The `active_tal_id` top-level field identifies which TAL is currently active for rendering. Build tools always append a new TAL; Realign targets a specific TAL by `tal_id`; Analyze may target one or multiple TALs for cross-alignment comparison. The agent is responsible for removing unwanted TALs after a decision is made.

### 4.3 Reference Data Is Read-Only
The application never writes to `geo`. Reference data updates are an operational concern handled outside the application.

### 4.4 Geocode Cache Is Non-Customer-Specific
The geocode cache maps normalized address strings to lat/lon coordinates and provider metadata. It contains no customer identifiers, account data, or territory data. It is safe to share across all customers.

### 4.5 TS Layer Cardinality
A valid TS may contain:
- 0-N point location layers
- 0-N territory alignment layers (TALs)

Examples:
- Geocode Address output: one point layer, no TAL
- Direct Build output: one new TAL appended; incoming point layers preserved
- Empty template TS: no point layers, no TAL
- Single-alignment planning TS: one TAL plus one or more point layers
- Comparative planning TS: two or more TALs (e.g., "By Revenue" and "By Headcount") plus shared point layers

### 4.6 TS In, TS Out
Geometry-bearing tools should accept a TS and return an updated TS whenever practical. The TS flows through the system and is adorned/augmented over time. For example, Geocode Address adds point layers, Auto Build appends a new TAL while preserving existing TALs and point layers, Realign updates a specific TAL identified by `tal_id`, and sharing renders the TS without changing it.

Exceptions must be justified in the Functional Spec.

### 4.7 TS Identity and Cache Handles
Every TS should carry identity metadata: `ts_id`, `revision`, `content_hash`, and `updated_at`. The `content_hash` must be computed over a canonicalized TS representation so agents and EZT MCP can detect whether a cached payload matches the caller's current TS.

Tools may accept either a full TS payload or a valid TS handle where appropriate. Tools that modify a TS must return updated identity metadata and must invalidate or supersede stale cache handles.

### 4.8 Presentation Metadata
A TS may include presentation metadata for one or more named views. Presentation metadata must be optional: a valid TS can render with default styles when no explicit presentation block is present.

Presentation metadata may define:
- layer visibility
- fill, stroke, opacity, and point symbol rules
- labels and minimum zooms
- classification method and breaks
- legend entries
- active/default view

Presentation metadata must not change analysis semantics. It affects rendering only.

---

## 5. Coding Conventions

### 5.1 Language and Style
- Python 3.12+ type hints on all function signatures
- `ruff` for linting and formatting
- No `Any` type annotations except where genuinely unavoidable; document why
- Async-first: all I/O-bound operations use `async/await`; no blocking calls in request handlers

### 5.2 Module Structure
```
ezt_mcp/
  server.py          — MCP server entry point
  tools/             — MCP tool implementations (one module per tool)
  resources/         — MCP resource implementations
  prompts/           — MCP prompt implementations
  retrieval/         — ExpertPack retrieval engine
  territory/         — Territory computation pipeline (partition, zone, realign, dissolve, repair)
  geocoder/          — Geocoding (provider routing, cache read/write)
  db/                — Resource Server access layer (connection pool, migrations)
  auth/              — API key validation, customer resolution
  audit/             — Audit log writes
  config.py          — Configuration loading (Key Vault in production, config.yaml in dev)
```

### 5.3 Error Handling
- All tool handlers return structured errors — never unhandled exceptions to the MCP client
- Error messages sent to clients must not leak internal implementation details (stack traces, SQL, internal service URLs)

### 5.4 Dependencies
- `pyproject.toml` is the single source of truth for dependencies
- Minimum necessary dependencies — justify every addition
- **Forbidden libraries:** none established yet; additions to this list require Constitution amendment

### 5.5 Configuration
- `config.yaml` is the local development configuration format (inherited from ep-mcp)
- Production configuration is sourced from Azure Key Vault; `config.yaml` is never present in production containers
- No hardcoded configuration values in application code

---

## 6. Testing Non-Negotiables

Testing strategy is **TBD** — to be defined and added to this document before the Implementation phase begins. At minimum, the strategy must address:
- Unit test coverage expectations
- Spatial algorithm integration test requirements (PostGIS fixture data)
- CI/CD test gate requirements
- Geocoder mock/stub strategy for tests

---

## 7. Deployment Non-Negotiables

### 7.1 Stateless Container
The MCP container image contains no customer data, no credentials, and no mutable state. Safe to terminate and replace at any time.

### 7.2 Zero-Downtime Deployment
Deployments must not require downtime. Azure Container Apps revision-based deployment is the mechanism. Database migrations must be backward-compatible with the running container version during the transition window.

### 7.3 Infra-as-Code
Infrastructure provisioning is delegated to Matt Root. All infrastructure must be defined as code. Manual Azure Portal changes to production infrastructure are forbidden after initial provisioning.

---

## 8. Repo Hygiene

- `CHANGELOG.md` is updated with every meaningful commit
- `VISION.md`, `CONSTITUTION.md`, `FUNCTIONAL_SPEC.md`, `TECHNICAL_SPEC.md` are upstream docs — deviations from implementation are noted in `CHANGELOG.md`
- Generated artifacts, local dev databases, and secrets are gitignored
- No EZT customer data, real account lists, or real territory alignments are ever committed to the repository
- Commit messages follow conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`)

---

*This document governs the EZT MCP project. Amendments require explicit version bump, date update, and a CHANGELOG entry.*
