# CONSTITUTION.md — EZT MCP Non-Negotiables

**Version:** 0.1.0
**Date:** 2026-04-24
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
| Database | PostgreSQL + PostGIS | All durable state and spatial computation |
| Vector search (production) | pgvector | ExpertPack retrieval index lives in Postgres |
| Vector search (local dev) | sqlite-vec | Local dev only; never deployed to production |
| Spatial / geo library | GeoPandas + Shapely | Territory computation pipeline |
| Geocoder | Internal geocoder service (HTTP) | MCP never calls geocoder providers directly |
| Containers | Azure Container Apps | Stateless MCP instances |
| Secrets (production) | Azure Key Vault | No plaintext credentials in config files or env vars in production |
| Infra-as-code | Delegated to Matt Root | Not defined here |
| Testing | TBD | To be defined before Implementation phase |

---

## 2. Architecture Non-Negotiables

### 2.1 Stateless MCP Tier
The EZT MCP application container is **fully stateless**. All durable state — territory alignments, account data, API keys, audit logs — lives in PostgreSQL. Container restarts and horizontal scaling must be transparent to clients.

### 2.2 Tenant Isolation — Schema-Per-Tenant
Each customer tenant has its own PostgreSQL schema (`tenant_{id}`). Tenant schemas are never read by queries executing in another tenant's context. The application resolves tenant identity from the API key on every request and sets the search path accordingly before any data access.

Shared reference data (ZIP code polygons, county polygons, state boundaries) lives in a separate `shared_geo` schema. The application user has read-only access to `shared_geo` and full access to the resolved tenant schema only.

An `mcp_admin` schema holds cross-tenant administrative tables (tenant registry, global audit log). Application code has no write access to `mcp_admin` at runtime; provisioning operations use a separate privileged path.

### 2.3 Geocoding Is an Internal Service Dependency
The MCP process never holds geocoder provider credentials (TomTom, Azure Maps). All geocoding is delegated to an internal geocoder service called over HTTP. The geocoder service owns provider selection, tier routing, and fallback logic. Geocoder tier (trial → Nominatim, paid → TomTom with Azure Maps fallback) is resolved by the geocoder service from tenant context passed by the MCP.

### 2.4 ExpertPack — Shared Base Pack
A single shared ExpertPack backs the knowledge layer for all tenants. It encodes territory design expertise, EZT product knowledge, and EZT MCP tool/workflow guidance. All tenants query the same pack. Per-tenant pack overlays are not in scope for v1.

---

## 3. Security Non-Negotiables

### 3.1 API Keys
- Every API key is tenant-scoped — a key grants access to exactly one tenant's data and nothing else
- Keys are stored **hashed** (bcrypt or Argon2) in the database — plaintext keys are never persisted anywhere
- Keys are transmitted in the `Authorization: Bearer <key>` header only — never in URLs, query parameters, or request bodies
- Keys support rotation: a new key can be issued before the old one is revoked, with a configurable grace period
- Key metadata (label, created_at, last_used_at, expires_at) is stored alongside the hash to support audit and rotation workflows

### 3.2 Audit Log
Every MCP tool call is logged with: `tenant_id`, `tool_name`, `timestamp`, `source_ip`, `success` (bool), `error_code` (if applicable). The audit log is append-only. No audit log records are deleted or modified by application code.

### 3.3 TLS
All external traffic is TLS-encrypted. No plain HTTP endpoints are exposed in any environment except local development on loopback.

### 3.4 No Credentials in Code or Config Files (Production)
In production, all secrets (database credentials, geocoder service URL/key, Azure Key Vault access) are sourced from Azure Key Vault. Config files may reference Key Vault secret names but never contain secret values. This rule applies to container image builds, CI/CD pipelines, and deployment scripts.

### 3.5 Principle of Least Privilege
The application database user has the minimum permissions required: read on `shared_geo`, read/write on the resolved `tenant_{id}` schema, no access to other tenant schemas, no access to `mcp_admin` at runtime. Geocoder credentials are held only by the geocoder service process.

### 3.6 No Direct External API Calls from Tenant Request Context
The MCP process may not make direct calls to external APIs (Azure Maps, TomTom, third-party services) from within a tenant request handler. All external dependencies are mediated through internal services. This limits credential exposure and blast radius.

---

## 4. Data Model Non-Negotiables

### 4.1 Terminology
The canonical customer-facing term for a named mapping of geographic parts to territories is **territory alignment**. This term is used in all tool names, resource names, API surface, documentation, and the ExpertPack. Do not use "territory solution," "project," or "plan" as synonyms in the MCP surface.

### 4.2 Hierarchical Alignment Model
Territory alignments are hierarchical. An alignment contains named groups at one or more levels (e.g. region → district → territory). Groups contain sub-groups or geographic parts. The data model must support arbitrary depth. Flat (single-level) alignments are a degenerate case of the hierarchical model, not a separate concept.

### 4.3 Roster Relationship
The data model must support a hierarchical user-to-alignment relationship (roster). The roster encodes ownership (which users own which territory groups), hierarchy (org structure that may drive alignment structure), and access scoping (what data a given user can see and edit). The precise schema is defined in the Functional Spec.

### 4.4 Reference Data Is Read-Only
Shared geographic reference data (ZIP codes, counties, states) is read-only from the application's perspective. The MCP never writes to `shared_geo`. Reference data updates are an operational concern handled outside the application.

---

## 5. Coding Conventions

### 5.1 Language and Style
- Python 3.12+ type hints on all function signatures
- `ruff` for linting and formatting (replaces black + flake8)
- No `Any` type annotations except where genuinely unavoidable; document why
- Async-first: all I/O-bound operations use `async/await`; no blocking calls in request handlers

### 5.2 Module Structure
Inherited from ep-mcp and extended:
- `ezt_mcp/server.py` — MCP server entry point
- `ezt_mcp/tools/` — MCP tool implementations (one module per tool group)
- `ezt_mcp/resources/` — MCP resource implementations
- `ezt_mcp/prompts/` — MCP prompt implementations
- `ezt_mcp/retrieval/` — ExpertPack retrieval engine (pgvector production path)
- `ezt_mcp/territory/` — Territory computation pipeline (partition, zone, realign)
- `ezt_mcp/geocoder/` — Internal geocoder service client
- `ezt_mcp/db/` — Database access layer (connection pool, schema resolution, migrations)
- `ezt_mcp/auth/` — API key validation, tenant resolution
- `ezt_mcp/audit/` — Audit log writes
- `ezt_mcp/config.py` — Configuration loading (Key Vault in production, config.yaml in dev)

### 5.3 Error Handling
- All tool handlers return structured errors — never unhandled exceptions to the MCP client
- Database errors, geocoder errors, and computation errors are caught, logged, and returned as typed MCP error responses
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
- Geocoder mock/stub strategy

---

## 7. Deployment Non-Negotiables

### 7.1 Stateless Container
The MCP container image contains no tenant data, no credentials, and no mutable state. It is safe to terminate and replace at any time.

### 7.2 Zero-Downtime Deployment
Deployments must not require downtime. Azure Container Apps revision-based deployment is the mechanism. Database migrations must be backward-compatible with the running container version during the transition window.

### 7.3 Infra-as-Code
Infrastructure provisioning is delegated to Matt Root. All infrastructure must be defined as code (tooling choice delegated). Manual Azure Portal changes to production infrastructure are forbidden after initial provisioning.

---

## 8. Repo Hygiene

- `CHANGELOG.md` is updated with every meaningful commit
- `VISION.md`, `CONSTITUTION.md`, `FUNCTIONAL_SPEC.md`, `TECHNICAL_SPEC.md` are upstream docs — if implementation deviates, the relevant doc is updated with a dated note explaining the deviation
- Generated artifacts, local dev databases, and secrets are gitignored
- No EZT customer data, real account lists, or real territory alignments are ever committed to the repository
- Commit messages follow conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`)

---

*This document governs the EZT MCP project. Amendments require explicit version bump, date update, and a CHANGELOG entry.*
