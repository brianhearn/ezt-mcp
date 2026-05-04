# CONSTITUTION.md — EZT MCP Non-Negotiables

**Version:** 0.2.0
**Date:** 2026-05-04
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
| Database | PostgreSQL + PostGIS | Part layers, geocode cache — shared reference data only |
| Spatial / geo library | GeoPandas + Shapely | Territory computation pipeline (dissolve, partition, zone, realign) |
| Containers | Azure Container Apps | Stateless MCP instances |
| Secrets (production) | Azure Key Vault | No plaintext credentials in config files or env vars in production |
| Infra-as-code | Delegated to Matt Root | Not defined here |
| Testing | TBD | To be defined before Implementation phase |

---

## 2. Architecture Non-Negotiables

### 2.1 Stateless MCP Tier
The EZT MCP application container is **fully stateless**. It holds no customer data, no territory solutions, no mutable per-request state. Postgres holds only shared reference data (part layers, geocode cache). Container restarts and horizontal scaling are transparent to clients.

### 2.2 No Per-Customer State in EZT MCP
EZT MCP does not store territory solutions, account data, or any customer-specific data. Customers provide inputs on each request; EZT MCP computes and returns results. The customer's agent is responsible for persisting outputs. This is a deliberate design choice — it eliminates data isolation complexity, reduces GDPR surface area, and keeps the Postgres footprint minimal.

### 2.3 Shared PostgreSQL — Reference Data Only
A single EasyTerritory-hosted PostgreSQL instance (PostGIS) serves all customers. It contains:
- `shared_geo` schema — part layer polygons (US ZIPs, US counties, US states, Canadian FSAs, etc.). Read-only from the application.
- `geocode_cache` schema — address → lat/lon cache. Shared across all customers; contains no customer-identifying data.

There are no per-customer schemas. The application user has read access to `shared_geo` and read/write access to `geocode_cache` only.

### 2.4 Geocoding — Internal to MCP
Geocoding is handled directly by EZT MCP (no separate geocoder microservice). Provider selection, tier routing, fallback, and cache lookup/write are all implemented within the MCP server. Provider credentials (TomTom, Azure Maps) are sourced from Azure Key Vault at startup.

Provider hierarchy: Nominatim (where ToS permits) → TomTom → Azure Maps fallback.

### 2.5 GeoJSON as the Universal Wire Format
All geometry-bearing inputs and outputs use GeoJSON. No other geometry format is accepted or produced. The canonical territory solution format is a GeoJSON `FeatureCollection` (see VISION.md). Tools that produce or consume territory data speak only GeoJSON.

The one exception: the Analyze Territory Solution tool returns structured JSON (no geometry in analysis output).

### 2.6 Dissolve Is an Internal Operation
Territory dissolution (union of geographic parts into a territory polygon) is an internal computation step, not an exposed MCP tool. It is implemented as a shared library function used by the Direct Build and Auto Build tools. The territory solution output always includes pre-dissolved geometry — the canonical format is self-contained and requires no separate part layer to render.

### 2.7 ExpertPack — Shared Knowledge Layer
A single shared ExpertPack backs the domain knowledge layer for all customers. All customers query the same pack. Per-customer pack overlays are not in scope for v1.

### 2.8 EasyTerritory Hosts Everything
EZT MCP infrastructure is hosted and operated by EasyTerritory. Customers are not responsible for deployment, Postgres, or part layer data. Customer access is via API key only.

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
The application database user has read access to `shared_geo` and read/write access to `geocode_cache` only. No other schemas. Geocoder provider credentials are loaded from Key Vault at startup and held in memory only.

### 3.6 No Customer Data Persisted
EZT MCP never writes customer territory solutions, account data, or alignment files to any persistent store. All customer data is transient — received in the request, used for computation, returned in the response, discarded.

---

## 4. Data Model Non-Negotiables

### 4.1 Terminology

| Term | Definition |
|---|---|
| **Part (P)** | A single geographic unit (e.g., one ZIP code polygon). The atomic unit of territory composition. |
| **Territory (T)** | The dissolved union of one or more parts assigned to a named territory. A T is a GeoJSON Feature with dissolved MultiPolygon geometry and `part_ids` in properties. |
| **Territory Solution (TS)** | A complete territory alignment — a GeoJSON FeatureCollection of Ts plus solution-level metadata. The canonical output of Direct Build and Auto Build. |
| **Part Layer** | A named collection of part polygons stored in `shared_geo` (e.g., `us_zips`, `us_counties`, `ca_fsa`). |
| **Alignment File** | A customer-supplied CSV or Excel file mapping part identifiers (e.g., ZIP codes) to territory names. Input to Direct Build. |

Use these terms consistently in all tool names, resource names, API surface, documentation, and the ExpertPack.

### 4.2 Territory Geometry Is Always Dissolved
A Territory feature always carries dissolved polygon geometry — the union of all its constituent parts. A TS is self-contained. `part_ids` records the composition but the geometry is pre-computed and embedded.

### 4.3 Reference Data Is Read-Only
The application never writes to `shared_geo`. Reference data updates are an operational concern handled outside the application.

### 4.4 Geocode Cache Is Non-Customer-Specific
The geocode cache maps address strings to lat/lon coordinates. It contains no customer identifiers, account data, or territory data. It is safe to share across all customers.

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
  territory/         — Territory computation pipeline (partition, zone, realign, dissolve)
  geocoder/          — Geocoding (provider routing, cache read/write)
  db/                — Database access layer (connection pool, migrations)
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
