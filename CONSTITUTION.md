# CONSTITUTION.md — EZT MCP Non-Negotiables

**Version:** 0.7.0
**Date:** 2026-05-07
**Status:** Draft

These are the architectural, security, stack, and convention decisions that are locked for the life of the project. Deviations require explicit revision of this document with justification. All downstream specs and implementation must conform.

---

## 1. Stack

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.12+ | No exceptions |
| MCP framework | FastMCP (official MCP SDK) | Inherited from ep-mcp |
| Web layer | Starlette + Uvicorn | Inherited from ep-mcp |
| CLI | Click | Inherited from ep-mcp |
| Resource Server | PostgreSQL + PostGIS | Part layers, self-hosted Nominatim + US reference data, geocode cache, spatial compute support — shared resources only |
| Spatial / geo library | GeoPandas + Shapely | Territory computation pipeline (dissolve, partition, zone, realign) |
| Containers | Azure Container Apps | Stateless MCP instances |
| Secrets (production) | Azure Key Vault | No plaintext credentials in config files or env vars in production |
| Infra-as-code | Delegated to Matt Root | Not defined here |
| Testing | TBD | To be defined before Implementation phase |

---

## 2. Architecture Non-Negotiables

### 2.1 Stateless MCP Tier
The EZT MCP application container is **durably stateless**. It holds no persistent customer data, no durable territory solutions, and no mutable customer state that must survive restart. The Resource Server holds only shared reference data and shared spatial infrastructure (part layers, self-hosted Nominatim + US datasets, geocode cache, spatial indexes/functions). Container restarts and horizontal scaling are transparent to clients except for optional short-lived cache misses.

### 2.2 No Per-Customer State in EZT MCP
EZT MCP does not persist territory solutions, account data, or any customer-specific data as a system of record. Every tool call supports the fully stateless path: the agent passes the current TS in, EZT MCP computes, the updated TS comes back out. For efficiency, the agent may use short-lived cache handles instead of repeatedly transmitting the same multi-MB TS. The agent is responsible for persisting outputs and for retrieving account data from the customer's source systems (CRM, spreadsheets, databases) before embedding it as a point layer.

This is a deliberate design choice — it minimizes data isolation complexity, reduces GDPR surface area, keeps the Resource Server footprint bounded, and keeps EZT MCP horizontally scalable. Short-lived cache entries are allowed only as a transport optimization and must not become durable customer storage.

### 2.3 Resource Server — Shared Spatial Infrastructure Only
A single EasyTerritory-hosted Resource Server, implemented as PostgreSQL/PostGIS, serves all customers. It contains:
- `shared_geo` schema — part layer polygons (US ZIPs, US counties, US states, Canadian FSAs, etc.). Read-only from the application.
- `nominatim` schemas/tables — self-hosted Nominatim geocoding data and indexes, including required US address/reference datasets.
- `geocode_cache` schema — address → lat/lon cache. Shared across all customers; contains no customer-identifying data.
- Spatial helper functions/indexes used by the territory computation pipeline when work is better performed in PostGIS than in the application container.

There are no per-customer schemas. The Resource Server is shared infrastructure, not customer storage. The application user has the minimum privileges required to read shared spatial resources, execute approved spatial helper functions, and read/write the geocode cache.

### 2.4 Geocoding — Internal to MCP
Geocoding is handled directly by EZT MCP (no separate geocoder microservice). Provider selection, tier routing, fallback, and cache lookup/write are all implemented within the MCP server. Provider credentials (TomTom, Azure Maps) are sourced from Azure Key Vault at startup.

Provider hierarchy: self-hosted Nominatim on the Resource Server → TomTom → Azure Maps fallback. Public Nominatim is not used for the hosted commercial service.

### 2.5 GeoJSON as the Universal Wire Format
The Territory Solution (TS) is standard GeoJSON — a `FeatureCollection` with EZT MCP conventions expressed in standard `properties` fields. It is not a proprietary format, a custom binary, or an EZT-specific file type. Any GeoJSON-aware tool or library can parse a TS without an EZT SDK.

All geometry-bearing inputs and outputs are TSes. Geocode Address returns a TS with point location features and no territory alignment layer. No other geometry format is accepted or produced. GeoJSON geometry follows RFC 7946.

The one exception: the Analyze Territory Solution tool returns structured JSON with no geometry, since analysis results are tabular. If those results need to travel with geometry, the agent can attach them back into a TS as properties or companion metadata in a later workflow.

### 2.6 Dissolve and Repair Are Internal Operations
Territory dissolution (union of geographic parts into a territory polygon) and Repair (hole-filling, contiguity restoration) are internal computation steps, not exposed MCP tools. They are implemented as shared library functions used by the build tools (Direct Build, Account Build, Auto Build) and Realign. The territory solution output always includes pre-dissolved geometry — the canonical format is self-contained and requires no separate part layer to render.

### 2.7 ExpertPack — Shared Knowledge Layer
A single shared ExpertPack backs the domain knowledge layer for all customers. All customers query the same pack. Per-customer pack overlays are not in scope for v1.

### 2.8 EasyTerritory Hosts Everything
EZT MCP infrastructure is hosted and operated by EasyTerritory. Customers are not responsible for deployment, the Resource Server, Nominatim, PostGIS, or part layer data. Customer access is via API key only.

### 2.9 Sharing Is Flagship, But Not System of Record
EZT MCP must support executive sharing workflows as a first-class flagship capability, but it must not become the system of record for customer Territory Solutions. Sharing surfaces are read-only projections of a TS supplied by the customer's agent or storage layer. Supported sharing directions include unified map-component views, Power BI-friendly projections/exports, and narrative executive summaries generated from TS + Analyze output.

Read-only sharing and assisted map selection must use the same underlying map component with capability flags/modes, not two divergent UI implementations.

### 2.10 Analysis Presentation Guidance Is Product Surface
Analyze Territory Solution returns structured JSON facts. EZT MCP must also provide agent-facing presentation guidance — as MCP resources/prompts and/or versioned markdown such as `ANALYSIS_DESIGN.md` — so calling agents can turn analysis JSON into clear, domain-appropriate operator insight.

This guidance is part of the product surface, not incidental documentation. It must be versioned, tested against example analysis outputs, and kept aligned with the Analysis tool schema.

### 2.11 Short-Lived TS Cache Is Allowed
TS payloads may be many MBs. EZT MCP may provide cache-check/cache-put/cache-handle behavior so agents can avoid repeatedly transmitting full TS payloads across sequential tool calls. This cache is permitted only as a TTL-bound transport optimization, not as durable storage or a customer system of record.

A cache miss must be safe and expected: the agent can always resend the full TS. Cache handles must be scoped to the customer/API key and must not be guessable.

### 2.12 TS Presentation Metadata and Styling
The Map Component must support declarative TS presentation metadata for lightweight but useful styling. Styling must travel with the TS as GeoJSON-compatible metadata and/or be resolved from versioned EZT MCP style resources/templates. The component must render the same style spec consistently in read-only `view` and assisted `select` modes.

V1 styling must stay intentionally smaller than EZT Designer: territory colors/boundaries/opacity, labels, point symbol styling, simple classification, legends, and named visualization presets. Full Designer-style symbology editing, complex filtering, clustering, hotspots, and print layouts are not required for v1 unless later specs explicitly add them.

### 2.13 DESIGN.md Product Design System
The repo must contain a `DESIGN.md` file that captures the EasyTerritory product design language for AI coding agents. `DESIGN.md` should follow the emerging AI-agent design-system pattern: YAML frontmatter for machine-readable tokens and Markdown prose for rationale, constraints, and component guidance.

EZT Designer V2 is the visual source of truth. The Map Component must use `DESIGN.md` for product chrome, controls, legends, panels, empty/loading/error states, and default visual language. TS presentation metadata remains responsible for solution-specific map symbology.

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
| **Territory Solution (TS)** | The universal EZT MCP geometry artifact — a GeoJSON FeatureCollection that may contain 0-N point location layers and 0-1 territory alignment layer (TAL), plus solution-level metadata. |
| **Part Layer** | A named collection of part polygons stored on the Resource Server in `shared_geo` (e.g., `us_zips`, `us_counties`, `ca_fsa`). |
| **Alignment File** | A customer-supplied CSV or Excel file mapping part identifiers (e.g., ZIP codes) to territory names. Input to Direct Build. |
| **Grouping Attribute** | A non-spatial attribute on an account record (e.g., sales manager name, territory name) used by Account Build to infer territory assignments. |
| **Realignment Instructions** | A set of directed part-move operations supplied to the Realign tool: move part P from territory A to territory B, or into a new territory. |
| **Point Layer** | A named collection of point features embedded in a TS (e.g., accounts, stores, service locations). A TS supports 0-N point layers. Each layer declares `metric_fields` — the attributes Analyze should aggregate. |
| **Metric Fields** | Attribute names on a point layer that carry quantitative values for analysis (e.g., `annual_revenue`, `account_count`). Declared at the layer level in the TS. |
| **Territory Alignment Layer (TAL)** | A named polygon layer inside a TS representing one territory alignment. A TS supports 0-N TALs. Each TAL has a stable `tal_id` and a human-readable `label`. Each territory feature within a TAL carries dissolved geometry and `part_ids`. |
| **Resource Server** | EasyTerritory-hosted PostgreSQL/PostGIS instance containing shared part layers, self-hosted Nominatim + US reference datasets, geocode cache, and approved spatial helper functions. It is not customer storage. |
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
The application never writes to `shared_geo` or Nominatim reference datasets. Reference data updates are an operational concern handled outside the application.

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
