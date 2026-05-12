# TECHNICAL_SPEC.md — EZT MCP Implementation Design

**Version:** 0.1.0
**Date:** 2026-05-12
**Status:** Draft — implementation architecture baseline

This document defines how EZT MCP implements the external behavior in [FUNCTIONAL_SPEC.md](FUNCTIONAL_SPEC.md) while obeying the non-negotiables in [CONSTITUTION.md](CONSTITUTION.md). It owns internal architecture, data flow, storage choices, algorithm design, testing strategy, observability, and deployment mechanics.

Executable request/response contracts live in [`schemas/`](schemas/). This document references those schemas but does not duplicate them.

---

## 1. Implementation Principles

1. **Functional contract first.** Tool handlers implement `FUNCTIONAL_SPEC.md`; schemas provide validation fixtures; this document explains internals only.
2. **Stateless by construction.** All customer TS/account/alignment data is either in the request, in memory during the request, in a short-lived scoped cache, or in the response.
3. **TS is the canonical work product.** Internal models may be typed Python objects, GeoDataFrames, or SQL rows, but tool boundaries always translate back to TS/TS handle output.
4. **Shared data stays shared.** PostgreSQL/PostGIS stores canonical part layers, geocode cache, spatial indexes/functions, audit logs, API key metadata, and map-session/cache coordination tables only. It is not customer storage.
5. **Small deterministic kernels.** Spatial operations are implemented as explicit pipeline steps with unit-testable functions: validate, materialize, assign, dissolve, repair, summarize, serialize.
6. **Async at service edges; bounded CPU work inside workers.** MCP and web handlers are async. CPU-heavy spatial work runs in bounded worker pools so request handlers do not block the event loop.
7. **Explainability beats cleverness.** Build and repair outputs include enough summaries, warnings, and lineage for agents to explain what changed.
8. **Example payloads are first-class tests.** `schemas/examples/` are contract fixtures and must stay valid as schemas evolve.

---

## 2. Runtime Architecture

### 2.1 Service topology

```text
MCP client / agent
  |
  | FastMCP tools/resources/prompts over HTTP/SSE or streamable transport
  v
EZT MCP container — Azure Container Apps
  |
  | async DB access + approved SQL functions
  v
PostgreSQL/PostGIS Resource Server
  |
  | static browser assets / PMTiles URLs
  v
Object/blob storage + CDN
```

The MCP container is horizontally scalable. Any instance can handle any stateless tool call when the caller supplies a full TS. Short-lived handles and map sessions are stored in a shared transient store so they work across instances.

### 2.2 Process layout

The application runs one Starlette/Uvicorn process hosting FastMCP and browser-facing map-session endpoints. Recommended production shape:

- `uvicorn` workers: sized by CPU and memory budget.
- async DB pool per process.
- bounded process/thread pool for GeoPandas/Shapely CPU work.
- request-level timeouts and maximum payload sizes.
- health endpoints for container readiness/liveness.

### 2.3 Module layout

```text
ezt_mcp/
  __init__.py
  server.py                    # FastMCP + Starlette app assembly
  config.py                    # env/dev config + Key Vault resolution
  errors.py                    # structured error model + safe exception mapping
  models/
    ts.py                      # typed TS/TAL/feature conventions
    tool_io.py                 # Pydantic or dataclass request/result models
    geometry.py                # internal geometry DTOs
  tools/
    geocode_address.py
    ingest_accounts.py
    direct_build.py
    account_build.py
    auto_build.py
    realign.py
    analyze.py
    map_session_create.py
  resources/
    part_layers.py             # available part-layer discovery resources
    map_sessions.py            # selection/state resources
    guidance.py                # analysis/design guidance resources
  prompts/
    territory_design.py
    analysis_presentation.py
  territory/
    parts.py                   # part-layer lookup and validation
    hierarchy.py               # territory_path tree materialization
    dissolve.py                # leaf + rollup geometry union
    repair.py                  # hole/contiguity repair pipeline
    metrics.py                 # rollup + territory aggregates
    workload.py                # travel/dwell/frequency workload model
    partition.py               # auto-build partitioning algorithms
    realign.py                 # directed part moves
    summarize.py               # stable result summaries/warnings
  geocoder/
    normalize.py
    cache.py
    tomtom.py
    azure_maps.py
    service.py                 # provider routing/fallback
  map_component/
    sessions.py                # session lifecycle, tokens, refresh events
    assets.py                  # URL/signing helpers for hosted MC assets
  db/
    pool.py
    migrations/
    repositories/
      part_layers.py
      geocode_cache.py
      api_keys.py
      audit_log.py
      transient_cache.py
      map_sessions.py
  auth/
    api_keys.py
    customer_context.py
  audit/
    logger.py
  observability/
    logging.py
    metrics.py
    tracing.py
  tests/
```

The exact file names can evolve, but these boundaries should hold: tools orchestrate; `territory/` computes; `db/` persists shared/transient infrastructure; models serialize boundaries.

---

## 3. Data Storage Design

### 3.1 PostgreSQL/PostGIS schemas

Recommended database schemas:

| Schema | Purpose | Customer data? |
|---|---|---|
| `geo` | Read-only canonical part layers. | No |
| `geocode_cache` | Shared normalized-address geocode cache. | No customer identifiers |
| `auth` | Hashed API keys and customer metadata. | Customer/account metadata only |
| `audit` | Append-only tool-call audit events. | Metadata only; no TS payloads |
| `transient` | TTL cache handles and map-session coordination. | Short-lived customer data allowed |
| `ops` | Migrations, app metadata, health/maintenance state. | No |

Only `geo`, `geocode_cache`, `auth`, `audit`, and `transient` are required for v1. `ops` is optional but useful for migrations and operational checks.

### 3.2 Part-layer tables

Canonical part layers live in `geo` and are read-only to the app user.

Recommended table shape per part layer:

```sql
geo.us_zips (
  part_id text primary key,
  label text,
  canonical_name text,
  country_code text,
  admin1 text,
  geom geometry(MultiPolygon, 4326),
  centroid geometry(Point, 4326),
  properties jsonb,
  updated_at timestamptz not null
)
```

Required indexes:

- primary key on `part_id`
- GiST on `geom`
- GiST on `centroid`
- optional btree indexes for common admin fields

Part layer availability should be discoverable through a metadata table:

```sql
geo.part_layers (
  part_layer text primary key,
  table_name text not null,
  label text not null,
  description text,
  country_codes text[] not null default '{}',
  admin_levels text[] not null default '{}',
  geometry_type text not null,
  srid integer not null default 4326,
  id_field text not null default 'part_id',
  id_format text,
  example_part_ids text[] not null default '{}',
  part_count integer,
  capabilities jsonb not null default '{}',
  data_version text,
  is_active boolean not null default true,
  updated_at timestamptz not null
)
```

`geo.part_layers.table_name` is internal metadata and must not be exposed through MCP resources. Public discovery resources return the stable `part_layer` ID plus safe descriptive fields only.

### 3.3 Geocode cache

```sql
geocode_cache.entries (
  normalized_key text primary key,
  provider text not null,
  provider_place_id text,
  latitude double precision not null,
  longitude double precision not null,
  confidence double precision,
  match_quality jsonb not null default '{}',
  raw_provider_metadata jsonb not null default '{}',
  first_seen_at timestamptz not null,
  last_used_at timestamptz not null,
  expires_at timestamptz
)
```

Do not store source row IDs, account names, customer IDs, or raw customer records. The normalized key should be an address normalization product, not a customer record.

### 3.4 API key metadata

```sql
auth.api_keys (
  key_id uuid primary key,
  customer_id uuid not null,
  label text not null,
  key_hash text not null,
  algorithm text not null,
  scopes text[] not null default '{}',
  created_at timestamptz not null,
  last_used_at timestamptz,
  expires_at timestamptz,
  revoked_at timestamptz
)
```

Key lookup should use a keyed prefix/identifier when available so the server does not bcrypt/Argon2-scan every key. Plaintext keys are never stored.

### 3.5 Audit log

```sql
audit.tool_calls (
  audit_id uuid primary key,
  customer_id uuid not null,
  key_id uuid,
  tool_name text not null,
  request_id text not null,
  source_ip inet,
  started_at timestamptz not null,
  duration_ms integer,
  success boolean not null,
  error_code text,
  input_summary jsonb not null default '{}',
  output_summary jsonb not null default '{}'
)
```

Audit summaries must not include raw account data, full addresses, full TS payloads, API keys, map tokens, or customer alignment files.

### 3.6 Short-lived TS cache

The transient TS cache is a transport optimization. Recommended implementation: PostgreSQL table with TOAST-compressed `bytea` or external Redis-compatible cache if Azure architecture chooses one. PostgreSQL is acceptable for v1 simplicity if TTL and payload-size limits are enforced.

```sql
transient.ts_cache (
  handle text primary key,
  customer_id uuid not null,
  content_hash text not null,
  revision integer,
  payload_compressed bytea not null,
  payload_bytes integer not null,
  created_at timestamptz not null,
  expires_at timestamptz not null,
  last_accessed_at timestamptz not null
)
```

Rules:

- handle is random, non-guessable, and scoped by customer/API key.
- max payload size is configurable.
- cache entries are excluded from backups where infrastructure permits.
- cache miss is normal and maps to `INVALID_TS_HANDLE`.
- mutations return a new handle and do not overwrite old handles in place.

### 3.7 Map sessions

```sql
transient.map_sessions (
  map_session_id text primary key,
  customer_id uuid not null,
  mode text not null,
  ts_handle text,
  ts_identity jsonb not null,
  active_tal_id text,
  presentation jsonb not null default '{}',
  interaction_flags jsonb not null default '{}',
  state jsonb not null default '{}',
  created_at timestamptz not null,
  expires_at timestamptz not null,
  revoked_at timestamptz
)

transient.map_session_events (
  event_id text primary key,
  map_session_id text not null references transient.map_sessions(map_session_id),
  event_type text not null,
  payload jsonb not null,
  created_at timestamptz not null
)
```

The TS referenced by a map session must remain short-lived. A read-only boss link or select-mode session is not durable storage.

---

## 4. TS Internal Representation

### 4.1 Parsing and validation

Incoming TS payloads are parsed into internal models:

- `TerritorySolution`
- `PointLayer`
- `TerritoryAlignmentLayer`
- `TerritoryFeature`
- `TsIdentity`
- `PresentationMetadata`

Validation has two tiers:

1. **Structural validation:** valid GeoJSON `FeatureCollection`, recognizable layer metadata, geometry types, required identity fields when expected.
2. **Semantic validation:** TAL IDs unique, territory IDs unique within TAL, parent references valid, no cycles, leaf/rollup constraints obeyed, part layers consistent, point/metric fields usable.

Full RFC 7946 validation can be staged; v1 should at least reject malformed geometry and non-FeatureCollection inputs before computation.

### 4.2 TS metadata conventions

A TS is a GeoJSON `FeatureCollection`. Recommended top-level `properties` shape:

```json
{
  "ts_id": "ts_...",
  "revision": 3,
  "content_hash": "sha256:...",
  "updated_at": "2026-05-12T19:40:00Z",
  "active_tal_id": "tal_...",
  "point_layers": [...],
  "tal_metadata": [...],
  "presentation": {...}
}
```

Territory and point features remain ordinary GeoJSON features. Layer membership is expressed in `properties`, not by non-standard GeoJSON containers.

### 4.3 Feature conventions

Territory feature required properties:

- `feature_kind: "territory"`
- `tal_id`
- `territory_id`
- `label`
- `depth`
- `parent_territory_id`
- `is_leaf`
- `part_ids`

Point feature required properties:

- `feature_kind: "point"`
- `point_layer`
- stable caller or generated row/account ID

The existing schemas intentionally keep TS GeoJSON permissive. These implementation conventions should later be promoted into a dedicated TS schema once stable.

### 4.4 Canonicalization and content hash

`content_hash` is computed over a canonical JSON representation:

1. Remove or ignore `content_hash` itself.
2. Normalize object key ordering.
3. Normalize numeric formatting as emitted by the serializer.
4. Sort metadata arrays by stable IDs where order is semantically irrelevant.
5. Sort features by `(feature_kind, tal_id or point_layer, territory_id or row_id)` where possible.
6. Serialize compact UTF-8 JSON.
7. Compute SHA-256 and prefix with `sha256:`.

If feature ordering is intentionally user-visible in a future surface, do not sort that portion. V1 should treat ordering as non-semantic.

### 4.5 Revision behavior

- Creating a new TS starts at revision `0` or `1`; choose one and keep it consistent in implementation tests.
- Mutating tools increment revision by 1.
- Non-mutating tools do not increment revision.
- Returning a handle for an unchanged TS does not increment revision.
- `updated_at` changes when the TS content changes.

---

## 5. Common Tool Execution Pipeline

Every tool handler follows the same skeleton:

1. Authenticate API key and create `CustomerContext`.
2. Parse request and validate against typed model/schema equivalent.
3. Resolve TS input:
   - use full `ts` when supplied;
   - otherwise load `ts_handle` from transient cache scoped to customer.
4. Validate optimistic concurrency if expected revision/hash is supplied.
5. Execute tool-specific pipeline.
6. Produce TS/result summaries and warnings.
7. Serialize updated TS or store it in transient cache and return `ts_handle` according to response-size policy.
8. Write audit log summary.
9. Map exceptions to structured errors.

### 5.1 Response-size policy

Tools may return either full `ts` or `ts_handle`. Recommended v1 policy:

- If serialized TS <= configurable inline threshold, return full TS and optionally a handle.
- If serialized TS > threshold, store in cache and return handle.
- Always return `ts_identity`.

The policy must be deterministic enough for tests but configurable for deployment.

### 5.2 Structured error mapping

Use internal exception classes that map exactly to common error codes:

- `InvalidTsError` → `INVALID_TS`
- `InvalidHandleError` → `INVALID_TS_HANDLE`
- `StaleRevisionError` → `STALE_TS_REVISION`
- `UnknownPartLayerError` → `UNKNOWN_PART_LAYER`
- `UnknownPartIdError` → `UNKNOWN_PART_ID`
- `UnknownTalError` → `UNKNOWN_TAL_ID`
- `AmbiguousTalError` → `AMBIGUOUS_TAL`
- `UnknownFieldError` → `UNKNOWN_FIELD`
- `ClarificationRequiredError` → `CLARIFICATION_REQUIRED`

Unhandled exceptions become `PROVIDER_UNAVAILABLE` only for dependency outages, otherwise a generic retryable=false structured failure with no stack trace in the response.

---

## 6. Territory Computation Pipeline

### 6.1 Part lookup

`territory.parts` resolves part IDs through the `geo.part_layers` registry and returns a GeoDataFrame with:

- `part_id`
- `geom`
- `centroid`
- optional properties

Lookups should batch by part layer and use parameterized SQL. Unknown IDs are reported as structured validation failures before expensive geometry work.

### 6.2 Part-layer discovery resources

`resources.part_layers` exposes safe MCP resources backed by `geo.part_layers`:

- `ezt://part-layers` lists active layers available to the caller.
- `ezt://part-layers/{part_layer}` returns detailed metadata for one layer.

Implementation rules:

1. Query only active rows the caller is allowed to use.
2. Return the stable `part_layer` ID and safe descriptive metadata.
3. Never expose `table_name`, SQL, database hostnames, storage URLs, credentials, or internal index/function names.
4. Include `capabilities` so agents know whether a layer can be used for build, realign, analyze, and map-selection workflows.
5. Cache metadata in-process briefly if desired, but invalidate or refresh on deployment/config changes.
6. Map unknown layers to `UNKNOWN_PART_LAYER`.

### 6.3 Territory tree materialization

`territory.hierarchy.materialize(paths)` converts Direct Build assignment rows into an internal tree.

Inputs:

- `part_id`
- `territory_path: list[str]`
- optional metadata

Algorithm:

1. Validate every path has 1–5 non-empty labels.
2. Normalize labels for identity generation while preserving display labels.
3. Build a trie keyed by path segment under the TAL root.
4. Each assignment attaches its `part_id` to the terminal node.
5. Nodes with direct parts are leaf nodes.
6. Nodes with children are rollup nodes and must not hold direct parts.
7. If a node both has children and direct parts, reject or split according to v1 policy. Recommended v1: reject with `CLARIFICATION_REQUIRED`, because mixed leaf/rollup semantics violate the Constitution.
8. Assign deterministic `territory_id`s from TAL ID + path slug + collision suffix.
9. Assign `depth`, `parent_territory_id`, and `is_leaf`.

Flat builds are just tries where every path has one segment; every node is a root leaf.

### 6.4 Leaf geometry dissolve

For every leaf territory:

1. Collect assigned part geometries.
2. Validate all parts exist in the selected `part_layer`.
3. Union part polygons with Shapely/GeoPandas.
4. Normalize to MultiPolygon.
5. Attach `part_ids` sorted for deterministic output.

PostGIS `ST_UnaryUnion` may be used for large territory dissolves if profiling shows it is faster or less memory-heavy than in-process Shapely. The implementation should hide that behind `dissolve_leaf_territory()` so the backend can be swapped.

### 6.5 Rollup geometry dissolve

For hierarchical TALs:

1. Process nodes bottom-up by descending depth.
2. For each rollup node, union child territory geometries.
3. Set `part_ids: []`.
4. Preserve child features; rollups are additional territory features, not replacements.

Rollup geometry is pre-dissolved and embedded so the Map Component can render without traversing part layers.

### 6.6 Repair pipeline

Repair is internal and applies after initial leaf dissolution or directed moves.

V1 repair phases:

1. **Geometry validity repair:** fix invalid polygons with safe geometry operations.
2. **Hole detection:** identify unassigned holes fully enclosed by a territory.
3. **Gap assignment:** assign small unassigned gaps to neighboring territories when policy allows.
4. **Contiguity check:** flag disconnected territories and optionally repair according to configured rules.
5. **Repair summary:** return counts and changed part IDs.

Repair policies:

- `strict`: fail on repair-requiring topology problems.
- `default`: apply safe repairs and warn.
- `report_only`: report repair candidates without changing assignments where feasible.

The exact topology heuristics should be implemented behind `RepairPolicy` and tested with fixture geometries.

---

## 7. Tool Implementation Designs

### 7.1 `geocode_address`

Pipeline:

1. Normalize input rows and address fields.
2. Skip rows with valid existing coordinates unless caller explicitly requests geocoding.
3. Compute normalized cache keys.
4. Batch read cache hits.
5. Route misses through TomTom Level 1.
6. Retry fallback-eligible failures through Azure Maps.
7. Write provider successes to shared cache.
8. Return row-level results and failures.

Provider adapters expose a common async interface:

```python
async def geocode(query: GeocodeQuery) -> GeocodeResult
```

Do not leak provider raw failures directly to callers. Keep provider metadata safe and summarized.

### 7.2 `ingest_accounts`

Pipeline:

1. Resolve or create base TS.
2. Validate row IDs and location fields.
3. Use coordinates where valid.
4. Geocode only rows needing coordinates and having sufficient address data.
5. Preserve non-geometry columns in point properties.
6. Attach layer metadata: point layer name/label, metric fields, dwell/frequency fields if declared.
7. Return updated TS identity, row counts, failures, and warnings.

Rows that cannot become valid points are represented in failure output; successful rows remain usable.

### 7.3 `direct_build`

Pipeline:

1. Resolve base TS or create an empty TS.
2. Validate `part_layer`.
3. Materialize assignment trie from `territory_path`.
4. Validate part IDs and detect duplicate part assignments.
5. Dissolve leaf territories from assigned parts.
6. Dissolve rollup territories bottom-up.
7. Run repair on leaf territory assignments/geometries.
8. Build TAL metadata with `part_layer`, label, max depth, territory counts.
9. Append TAL features and metadata to TS.
10. Set `active_tal_id` to the new TAL.
11. Compute TS identity and return summary.

Duplicate part assignment v1 policy: fail with `CLARIFICATION_REQUIRED` unless all duplicate assignments point to the same leaf path, in which case de-duplicate and warn.

### 7.4 `account_build`

Pipeline:

1. Resolve TS and point layer.
2. Validate grouping field exists and is usable.
3. Spatially join account points to parts in the selected part layer.
4. Aggregate part ownership by grouping value.
5. Resolve conflicts where accounts in one part map to multiple groups.
6. Assign each part to a territory/group.
7. Dissolve, repair, append TAL, and summarize.

Conflict resolution should be policy-driven. Recommended v1 default: assign a part to the group with the highest account count in that part; ties produce warnings and deterministic tie-break by label.

### 7.5 `auto_build`

`auto_build` has three modes sharing common preparation.

Common preparation:

1. Resolve TS and point layer.
2. Spatially join points to parts.
3. Compute per-part measures:
   - account count;
   - metric sum for the selected metric;
   - workload contribution when workload is active;
   - centroid and adjacency hints.
4. Validate objective/bias and dwell/frequency fields.

Mode A — fixed territory count:

1. Use requested N.
2. Partition parts into N contiguous-ish zones minimizing weighted objective variance.
3. Dissolve/repair/append TAL.

Mode B — fixed workload target:

1. Compute total workload.
2. Derive N from target and variant.
3. Warn with derived territory count.
4. Partition as Mode A using derived N and workload constraints.

Scoped Split:

1. Load source TAL and source leaf territory.
2. Restrict candidate parts to the source territory's `part_ids`.
3. Build replacement territories inside that scope.
4. Copy all other territories from the source TAL.
5. Recompute necessary rollups if source TAL is hierarchical.
6. Append a derived TAL.

Partition algorithm baseline:

- Build a weighted graph of parts using spatial adjacency and centroid distances.
- Seed territories using k-medoids or farthest-point seeds weighted by workload/metric.
- Grow regions through adjacent parts while minimizing objective imbalance and shape penalties.
- Run local swap/refinement passes.
- Run repair/contiguity enforcement.

This is intentionally an implementation baseline, not a promise of exact optimization. The public guarantee is a best-effort balanced TAL with warnings for tension/outliers.

### 7.6 `realign`

Pipeline:

1. Resolve TS and validate expected identity.
2. Find target TAL by `tal_id`.
3. Ensure target TAL's part layer matches supplied/inferred `part_layer`.
4. Validate all moved parts exist and currently belong to leaf territories.
5. Validate target territories are leaf territories.
6. Apply directed moves in memory.
7. Re-dissolve changed leaf territories.
8. Recompute ancestor rollups for all affected branches.
9. Run repair according to policy.
10. Update TS identity.
11. If `map_session_id` is present, enqueue refresh event.

V1 does not move parts into rollup territories. If a user intends to move an entire branch, the agent must expand that into explicit leaf-part moves.

### 7.7 `analyze`

Pipeline:

1. Resolve TS and target TALs.
2. Validate metric fields and point layers when present.
3. For each TAL:
   - aggregate part counts from leaf territories;
   - spatially assign point features to leaf territories when point layers exist;
   - compute metric totals and workload totals;
   - compute rollup metrics bottom-up;
   - compute balance scores over leaf territories only;
   - detect leaf outliers.
4. Apply optional `scope` to produce selection aggregates.
5. Apply optional hypothetical moves on a copied in-memory assignment map and recompute affected metrics.
6. Produce caveats and presentation guidance URI.

Geography-only analysis is valid. In that case point-derived metrics are null/omitted but part counts, territory counts, hierarchy summaries, and topology caveats can still be returned.

### 7.8 `map_session_create`

Pipeline:

1. Resolve TS and active TAL.
2. Validate requested mode and presentation context.
3. Store or reuse a short-lived TS handle for the session.
4. Create `transient.map_sessions` row.
5. Issue browser-safe session token distinct from MCP API key.
6. Return MC URL and resource URIs.

Browser-facing endpoints validate the session token, never the MCP API key. Select-mode commits write `map_session_events` and update latest selection state. Resource subscriptions notify the agent when selection/state changes.

---

## 8. Map Component Session Implementation

### 8.1 Session token model

`map_url` contains only a short-lived map-session token or exchange code. Token requirements:

- random/non-guessable;
- scoped to `map_session_id` and customer;
- expires no later than session expiry;
- revocable by deleting/revoking the session row;
- never logs in full.

### 8.2 Resource state

`ezt://map-sessions/{id}/selection` returns the latest committed selection event, not transient hover/lasso state.

`ezt://map-sessions/{id}/state` returns session status, active TAL, expiry, current TS identity, last selection status, and last refresh status.

### 8.3 Refresh events

After successful Realign with a valid `map_session_id`:

1. Tool stores updated TS/handle.
2. Tool updates session state with new TS identity.
3. Tool writes a refresh event.
4. Browser receives refresh through WebSocket/SSE/polling implementation detail.
5. MCP resource state reflects refresh status.

The map session never becomes durable TS storage; the agent must persist the updated TS.

---

## 9. ExpertPack Integration

EZT MCP retains the ExpertPack retrieval layer as shared domain knowledge. Implementation surfaces:

- `ep_search` or equivalent knowledge retrieval tool/resource if kept from EP MCP.
- guidance resources for analysis presentation and territory design decisions.
- internal prompts for tool-use guidance only when they do not override structured tool facts.

Rules:

- Retrieval may help agents explain or decide, but it does not change deterministic tool outputs.
- Shared ExpertPack content is customer-agnostic.
- Tool handlers should not depend on LLM calls for core spatial computation.

---

## 10. Security Implementation

### 10.1 Authentication

All MCP calls require `Authorization: Bearer <api_key>`. Authentication middleware resolves:

- `customer_id`
- `key_id`
- scopes/permissions
- request ID

Browser map-session calls use session tokens, not API keys.

### 10.2 Authorization

V1 authorization is customer/API-key scoped:

- TS handles must match the authenticated customer.
- map sessions must match the authenticated customer for MCP resources and match the browser token for browser calls.
- API scopes can gate tools if product packaging requires it.

### 10.3 Logging safety

Never log:

- API keys or bearer headers;
- browser session tokens;
- full TS payloads;
- raw account rows;
- full address lists;
- customer alignment files.

Safe logs include IDs, counts, timings, error codes, geometry counts, and redacted summaries.

### 10.4 Dependency secrets

Production secrets come from Azure Key Vault:

- database credentials;
- TomTom key;
- Azure Maps credentials;
- token-signing key;
- any provider/API credentials.

Local development can use `config.yaml` or environment variables, but sample config must contain placeholders only.

---

## 11. Observability

### 11.1 Structured logs

Every request log should include:

- `request_id`
- `customer_id`
- `tool_name` or resource name
- `duration_ms`
- `success`
- `error_code`
- counts: features, parts, territories, rows, warnings

### 11.2 Metrics

Recommended Prometheus/OpenTelemetry metrics:

- request count/duration by tool and status;
- error count by code;
- TS payload bytes in/out;
- cache hit/miss count;
- geocode cache hit/miss/provider/failure count;
- part lookup duration;
- dissolve/repair duration;
- auto-build duration and part count;
- map-session active count and expired count;
- DB pool usage.

### 11.3 Tracing

Trace spans should align with pipeline phases:

- auth;
- request validation;
- TS resolve/cache;
- part lookup;
- spatial join;
- dissolve;
- repair;
- cache write;
- audit write.

Span attributes must be safe summaries only.

---

## 12. Performance and Limits

Initial configurable limits:

| Limit | Purpose |
|---|---|
| max request body bytes | protect MCP tier |
| max inline TS response bytes | decide TS vs handle |
| max TS cache bytes per entry | prevent transient-store abuse |
| max assignment rows | bound Direct Build |
| max account rows | bound Ingest/Auto Build |
| max parts per TAL | bound dissolve/repair |
| max map session TTL | enforce sharing security |
| max geocode batch size | protect providers |
| max concurrent spatial jobs | protect CPU/memory |

Large jobs should fail fast with structured guidance or move to an async job pattern in a future version. V1 tools can be synchronous if limits are reasonable.

### 12.1 Geometry performance strategy

- Use bounding-box prefilters and spatial indexes for joins.
- Batch part lookups.
- Prefer unary union over repeated pairwise union.
- Cache per-part geometry only when safe and non-customer-specific.
- Profile Shapely vs PostGIS dissolve for large inputs before committing to one backend everywhere.

---

## 13. Testing Strategy

### 13.1 Contract tests

- Validate every `schemas/examples/*.json` through `schemas/validate_examples.py`.
- Add negative examples for common error envelopes before implementation freeze.
- Run JSON parsing and schema validation in CI.

### 13.2 Unit tests

Required units:

- TS canonicalization/content hash;
- TS identity/revision behavior;
- TS handle scoping and TTL behavior;
- `territory_path` trie materialization;
- hierarchy cycle/leaf/rollup validation;
- duplicate assignment handling;
- repair policy decision logic;
- workload formula;
- metric aggregation and rollup sums;
- structured error mapping.

### 13.3 Spatial integration tests

Use tiny synthetic fixture part layers checked into the repo or generated at test time. Fixtures should cover:

- adjacent square polygons;
- holes/gaps;
- disconnected islands;
- hierarchical rollups;
- point-in-polygon joins;
- realign recomputing affected rollups.

Do not commit real customer data.

### 13.4 Provider tests

- Mock TomTom and Azure Maps adapters.
- Test cache hit, provider success, fallback success, partial failures, and provider outage.
- No live provider calls in default CI.

### 13.5 End-to-end smoke tests

Once implementation exists, smoke-test the main workflow:

1. ingest small account CSV fixture;
2. direct_build flat TAL;
3. direct_build hierarchical TAL;
4. auto_build Mode A;
5. analyze active TAL;
6. create select map session;
7. realign selected parts;
8. analyze scoped impact.

---

## 14. Migrations and Deployment

### 14.1 Migration policy

- Use explicit versioned migrations.
- Migrations must be backward-compatible during Azure Container Apps revision rollout.
- Never require downtime for production.
- Reference data updates to `geo` are operational data pipeline tasks, not app migrations.

### 14.2 Container contents

The container image includes:

- Python application code;
- static Map Component build artifacts if served by the app, or asset references if served from blob/CDN;
- schema files and guidance markdown resources;
- no customer data;
- no secrets.

### 14.3 Configuration

Configuration sources:

- local dev: `config.yaml` and/or environment variables;
- production: Azure Key Vault + environment references;
- tests: isolated test config with fake providers and temporary DB.

Config should validate at startup and fail fast when required production secrets or DB connectivity are missing.

---

## 15. Implementation Sequence

Recommended implementation order:

1. Project scaffold and CI gates.
2. Shared models: TS parse/serialize, identity, structured errors.
3. Schema/example validation in CI.
4. DB pool and repositories for part layers, transient cache, audit log.
5. Direct Build flat path.
6. Direct Build hierarchical path and rollup geometry.
7. Analyze for Direct Build outputs.
8. Realign for leaf moves.
9. Map session create + selection/state resources.
10. Ingest Accounts + geocoder cache/provider mocks.
11. Account Build.
12. Auto Build Mode A.
13. Auto Build Mode B.
14. Auto Build Scoped Split.
15. Analysis presentation guidance resources/prompts.
16. Production hardening: auth, Key Vault, observability, limits, deployment manifests.

This sequence intentionally starts with Direct Build because it exercises the TS/TAL/hierarchy core without requiring account ingestion, geocoding, or optimization algorithms.

---

## 16. Open Technical Questions

These are implementation questions, not product-contract blockers:

1. **Transient cache backend:** PostgreSQL-only for v1 simplicity, or Redis-compatible cache for lower latency and easier TTL eviction?
2. **Geometry backend threshold:** when should dissolve/repair run in Shapely vs PostGIS?
3. **Auto-build optimizer baseline:** which initial heuristic gives the best balance of quality, explainability, and implementation speed?
4. **Map Component asset hosting:** serve from MCP container for v1 or from blob/CDN from the start?
5. **Async job model:** are synchronous tool calls sufficient for expected v1 row/part counts, or should large builds return job resources?
6. **Dedicated TS JSON Schema:** when to promote implementation TS conventions into an executable schema stricter than the current permissive placeholder?

None of these should change the v1 external contracts unless later evidence proves a contract is infeasible.

---

## 17. Definition of Done for Implementation Start

Before writing production tool code, the repo should have:

- `pyproject.toml` with pinned baseline dependencies and dev tools;
- CI running JSON/schema validation, lint, typecheck, and tests;
- synthetic spatial fixtures;
- DB migration strategy chosen;
- local dev config template with placeholders only;
- structured error model implemented;
- TS canonicalization tests passing;
- Direct Build hierarchy unit tests passing.

---

*This Technical Spec is the implementation baseline. If implementation discovers a client-visible behavior change, update `FUNCTIONAL_SPEC.md` and schemas first, then revise this document.*
