# TECHNICAL_SPEC.md — EZT MCP Implementation Design

**Version:** 0.4.1
**Date:** 2026-05-15
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
6. **Async jobs for customer-data compute.** Customer-data compute tools are submitted as jobs and return immediately with a job/task reference. Request handlers never run long geocoding, spatial join, dissolve, repair, or analysis work inline.
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

The MCP container is horizontally scalable. Any instance can accept a tool submission, status read, result read, or cancellation request when the caller is authorized. Short-lived handles, jobs, progress events, results, and map sessions are stored in shared transient/customer-scoped storage so they work across instances.

### 2.2 Process layout

The application runs one Starlette/Uvicorn process hosting FastMCP and browser-facing map-session endpoints. Recommended production shape:

- `uvicorn` workers: sized by CPU and memory budget.
- async DB pool per process.
- bounded process/thread pool for GeoPandas/Shapely CPU work.
- background workers that claim queued jobs from shared transient storage.
- request-level timeouts and maximum payload sizes for submission/status/result calls.
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
    get_map_visualization.py
    request_part_selection.py
    get_part_selection.py
    create_territory_from_parts.py
    query_parts.py
    set_map_state.py
    get_map_selection.py              # compatibility/session-level helper
  resources/
    part_layers.py             # available part-layer discovery resources
    map_sessions.py            # map state resources
    part_selections.py         # first-class part-selection task resources
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
    sessions.py                # persistent session lifecycle, tokens
    session_store.py           # Postgres backing for mc_sessions table, events, state machine
    selection_store.py         # first-class selection tasks + committed part selections
    sse.py                     # SSE command channel for server-push events (mode_changed, tal_updated, job_progress, etc.)
    assets.py                  # URL/signing helpers for hosted MC assets
  db/
    pool.py
    migrations/
    repositories/
      part_layers.py
      geocode_cache.py
      api_keys.py
      audit_log.py
      jobs.py                      # async job state/progress/result records
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
| `transient` | TTL jobs, progress events, result handles, cache handles, and map-session coordination. | Short-lived customer data allowed |
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

### 3.7 Async jobs and progress

All customer-data compute tools create short-lived, customer-scoped jobs. PostgreSQL is acceptable for v1 queue/state storage; the schema may later move to a dedicated queue without changing the external job contract.

```sql
transient.jobs (
  job_id text primary key,
  customer_id uuid not null,
  key_id uuid,
  tool_name text not null,
  status text not null, -- queued|running|input_required|completed|failed|cancelled|expired
  phase text not null,
  status_message text,
  progress double precision not null default 0,
  total double precision,
  poll_interval_ms integer not null default 2000,
  priority integer not null default 100,
  idempotency_key text,
  request_summary jsonb not null default '{}',
  result_summary jsonb not null default '{}',
  result_handle text,
  error jsonb,
  cancel_requested boolean not null default false,
  leased_by text,
  lease_expires_at timestamptz,
  created_at timestamptz not null,
  started_at timestamptz,
  last_progress_at timestamptz not null,
  completed_at timestamptz,
  expires_at timestamptz not null
)

transient.job_events (
  event_id text primary key,
  job_id text not null references transient.jobs(job_id),
  customer_id uuid not null,
  sequence integer not null,
  event_type text not null, -- progress|warning|phase|result|error|cancel
  phase text,
  progress double precision,
  total double precision,
  message text,
  details jsonb not null default '{}',
  created_at timestamptz not null
)

transient.job_results (
  result_handle text primary key,
  job_id text not null references transient.jobs(job_id),
  customer_id uuid not null,
  content_type text not null,
  payload_compressed bytea not null,
  payload_bytes integer not null,
  created_at timestamptz not null,
  expires_at timestamptz not null
)
```

Rules:

- `customer_id` is part of every authorization check for job status, progress, result, cancellation, and cleanup.
- Request summaries, progress details, and result summaries must contain counts/status only, never full TS payloads, account rows, full address lists, API keys, browser tokens, or raw customer files.
- Results that include a TS should normally return a `ts_handle`; inline result payloads are allowed only under the configured size threshold.
- Job/result TTLs are short-lived transport conveniences, not durable customer storage.
- Workers claim jobs with row locking / leases (`FOR UPDATE SKIP LOCKED`) and heartbeat progress; expired leases can be retried according to per-tool idempotency rules.
- Full queued request payloads are stored in `transient.job_payloads`; `request_summary` may reference `payload_handle`/payload size metadata but must not embed full customer payloads.
- Expired transient job payloads/results and terminal job rows are removed by worker-driven cleanup so TTL storage remains bounded.

### 3.7.1 Current worker implementation notes

The deployed implementation runs a startup `JobWorker` in `ezt_mcp/workers.py`. On submission, `direct_build` and `create_territory_from_parts` persist a queued job and return immediately. Full queued request payloads are stored in `transient.job_payloads` and referenced from `transient.jobs.payload_handle` / `request_summary.payload_handle`; `request_summary` remains summary metadata only. The worker claims eligible rows from `transient.jobs`, dispatches by `tool_name`, hydrates the payload, runs the Direct Build worker pipeline, updates job progress/results, and publishes best-effort Map Component progress events when the queued request includes `map_session_id`.

Claims set/extend a lease. If a worker dies after a job has transitioned to `running`, a later worker may reclaim the job once `lease_expires_at` has passed and `next_attempt_at` has arrived. Reclaimed jobs keep the same `job_id`, increment `attempt_count`, use configurable backoff, and fail with `JOB_ATTEMPTS_EXHAUSTED` once `max_attempts` is reached. Direct Build/create-territory execution must remain idempotent with respect to the transient TS/result model.

Submission enforces configurable per-customer limits for active jobs and queued jobs. This removes per-request compute tasks from the HTTP/MCP submission path while preserving the existing job status/result contract. Workers periodically call `cleanup_expired()` to expire stale non-terminal jobs and delete expired `transient.job_payloads`, `transient.job_results`, and terminal job rows. Remaining production hardening item: cross-customer round-robin scheduling across multiple customers.

### 3.8 Map sessions (persistent per-user workspace + SSE)

```sql
transient.map_sessions (
  map_session_id text primary key,
  token text not null,
  user_id text not null,
  mode text not null,
  theme text not null default 'dark',
  active_tal_id text not null,
  active_tal_label text,
  ts_identity jsonb not null,
  render_payload jsonb not null,
  ts jsonb not null,
  presentation jsonb not null default '{}',
  public_base_url text not null default '',
  state_resource_uri text not null,
  selection_resource_uri text,
  pending_job_reference jsonb,
  committed_selection jsonb,
  active_selection_task_id text,
  created_at timestamptz not null,
  updated_at timestamptz,
  expires_at timestamptz not null
)
```

The current implementation enforces one active unexpired map session per `user_id`. `AsyncpgMapSessionStore` reconstructs the browser render payload from the persisted source TS, active TAL, presentation, and theme so render payloads do not become stale after code changes. SSE queues remain process-local and best-effort; durable row state is authoritative for session survival across service restarts.

`theme` is session-level presentation state. Agents set it with `presentation.style_overrides.theme` (`dark` or `light`); `dark` is the default for development/testing and for callers that do not explicitly request light.

A future `transient.map_session_events` table may persist cross-process browser push history if the deployment becomes horizontally scaled. For the current single-process deploy/testbed, live SSE fanout is in-process only and progress events are advisory UI hints.

The TS referenced by a map session must remain short-lived. A read-only boss link or select-mode session is not durable customer storage.

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

V1 customer-data compute tools are job submissions. The MCP request handler is a short control-plane operation; heavy work happens in background workers.

Submission handler skeleton:

1. Authenticate API key and create `CustomerContext`.
2. Parse request and validate against typed model/schema equivalent.
3. Validate request size and per-customer queue/active-job limits.
4. Store any large supplied TS payload in customer-scoped transient cache, or verify that supplied `ts_handle` exists and belongs to the customer.
5. Create a `transient.jobs` row with safe request summary, initial phase, TTL, and optional idempotency key.
6. Enqueue or leave queued for workers to claim.
7. Write audit log summary for job submission.
8. Return a job/task reference immediately with status/resource/result URIs and recommended poll interval.

Worker execution skeleton:

1. Claim a queued job with a lease using customer/global fairness rules.
2. Resolve TS input from customer-scoped cache or embedded job payload reference.
3. Validate optimistic concurrency if expected revision/hash is supplied.
4. Execute tool-specific pipeline in explicit phases, writing progress events after each phase/batch.
5. Serialize updated TS or store it in transient cache and return `ts_handle` according to response-size policy.
6. Store terminal result summary/result handle and mark job `completed`, `failed`, or `cancelled`.
7. Write audit log completion summary.
8. Map exceptions to structured errors without leaking internals.

Job status/result/cancel handlers are also control-plane operations and must authorize by `customer_id` on every access.

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

### 5.3 Job progress contract

Every job reports progress using durable phases and monotonic progress values. Pull status is authoritative; push progress is best-effort.

Status payloads include at minimum:

- `job_id`;
- `tool_name`;
- `status`: `queued`, `running`, `input_required`, `awaiting_user_selection`, `completed`, `failed`, `cancelled`, or `expired`;
- `phase`;
- `progress` and optional `total`;
- human-readable `status_message`;
- safe `counts`/summary fields;
- `created_at`, `last_progress_at`, and optional terminal timestamp;
- `poll_interval_ms`;
- `result_resource_uri` when terminal success has a result.

When the MCP caller supplies `_meta.progressToken`, the server should also send `notifications/progress` for important phase/batch updates. Those notifications must mirror persisted job events and must stop after terminal status.

Recommended phase names:

- Common: `accepted`, `queued`, `resolving_ts`, `validating_request`, `writing_result`, `completed`, `failed`, `cancelled`.
- Geocode/Ingest: `normalizing_rows`, `geocode_cache_lookup`, `provider_geocoding`, `provider_fallback`, `building_point_layer`.
- Build/Realign: `validating_part_layer`, `fetching_part_geometries`, `spatial_join`, `materializing_hierarchy`, `dissolving_leaf_territories`, `dissolving_rollups`, `repairing_topology`, `updating_ts_identity`.
- Analyze: `resolving_tals`, `spatially_assigning_points`, `aggregating_metrics`, `computing_rollups`, `computing_balance_scores`, `building_analysis_result`.

### 5.4 Job cancellation

Cancellation is cooperative. `job_cancel` or MCP `tasks/cancel` sets `cancel_requested=true`; workers check it between batches and expensive pipeline stages. A single GEOS/Shapely/PostGIS operation may not be interruptible once started, but no subsequent stage should begin after cancellation is observed. Cancelled jobs keep a safe terminal summary until TTL expiry.

### 5.5 Concurrency and tenant fairness

The scheduler enforces all of the following before starting work:

- global max active jobs;
- global max active spatial jobs;
- global max active geocode/provider jobs;
- DB pool and PostGIS query concurrency limits;
- per-customer max active jobs and queued jobs;
- per-customer max active spatial/geocode jobs;
- per-customer and provider geocoding rate limits;
- max request/result/cache bytes per customer.

Use separate execution pools for workload classes:

- **Geocoding:** I/O-bound, provider-rate-limited, retry/backoff, higher concurrency but per-customer/provider throttled.
- **Spatial build/realign/analyze:** CPU/memory/PostGIS-heavy, low concurrency, bounded process pool or PostGIS worker slots.
- **Control plane:** submission/status/result/cancel, high concurrency, no heavy work.

Fairness requirement: queue selection must prevent one customer's large batch from starving other customers. A simple v1 policy can round-robin eligible customers, then claim oldest eligible job per customer with `FOR UPDATE SKIP LOCKED`.

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

1. Accept request and create a customer-scoped async job record.
2. Return the job submission envelope immediately; run the worker in the background.
3. Resolve base TS or create an empty TS.
4. Validate `part_layer` against the closed public layer registry/mapping.
5. Materialize assignment trie from `territory_path`.
6. Validate part IDs and detect duplicate part assignments.
7. Fetch part geometries server-side from PostGIS; never return raw part geometry through interrogation tools.
8. Dissolve leaf territories from assigned parts.
9. Dissolve rollup territories bottom-up.
10. Run repair on leaf territory assignments/geometries.
11. Build TAL metadata with `part_layer`, label, max depth, territory counts.
12. Append TAL features and metadata to TS.
13. Set `active_tal_id` to the new TAL.
14. Compute TS identity and complete the job result.

Duplicate part assignment v1 policy: fail with `CLARIFICATION_REQUIRED` unless all duplicate assignments point to the same leaf path, in which case de-duplicate and warn.

Current implementation note: the first deployed worker uses process-local `asyncio.create_task` execution behind the persisted job contract. This is sufficient for the deploy/testbed path, but production should move execution to a durable worker/queue so in-flight jobs survive process restarts.

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

### 7.8 `get_map_visualization`

`get_map_visualization` is the first-class visual validation surface for all TS/TAL-producing work. Implement it early so Direct Build, Realign, Auto Build, and Analyze outputs can be inspected on the MC during development rather than validated only from JSON.

Pipeline:

1. Resolve TS and active TAL.
2. Validate requested mode and presentation context.
3. Store or reuse a short-lived TS handle for the session.
4. Create `transient.map_sessions` row.
5. Issue browser-safe session token distinct from MCP API key.
6. Return MC URL and resource URIs.

Browser-facing endpoints validate the session token, never the MCP API key. Select-mode commits write `map_session_events` and update latest selection state. Resource subscriptions notify the agent when selection/state changes.

Implementation minimum for the development loop:

- render supplied TS polygon features for the active TAL;
- when the TS has multiple TALs, include non-active TAL features in a separate reference overlay rendered below the active TAL with dimmed fill/stroke and no active labels;
- fit map bounds to visible TS geometry, including dimmed reference TALs so reviewers see full TS context;
- show labels/basic territory style from TS presentation metadata or defaults;
- support `view` mode first;
- return a URL embeddable in OpenClaw Canvas or directly openable in a browser;
- expose enough state to confirm TS identity, active TAL, available/reference TAL summaries, feature count, and expiry;
- persist the source TS or TS handle in the map session so browser-side Active TAL switching can rebuild the render payload server-side.

`select` mode, committed selection resources, and Realign refresh events can layer on after the read-only visualization loop is usable.

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

### 8.3 Presentation templates and panel context

The Map Component uses a presentation resolution stack:

1. Built-in EZT MCP presentation templates;
2. TS `properties.presentation.views[view_name]` metadata;
3. request-time `presentation.style_overrides`.

The initial built-in templates are:

- `qa_verification` — QA/development review, geometry counts, bounds/build diagnostics, debug panel enabled by default;
- `executive_review` — clean stakeholder review, summary/legend, debug panel disabled by default;
- `selection` — human spatial input, prompt/selection context, debug panel disabled by default.

The upper-left panel is a template-driven context panel, not arbitrary agent-generated chrome. Agents may pass title/subtitle/summary/legend/debug hints through presentation metadata, but the MC owns layout and product styling per `DESIGN.md`. The debug panel is controlled by `debug_panel` in the resolved presentation payload and should default off outside QA contexts. Customer-visible viewer strings are resolved from `presentation.chrome_labels` with built-in defaults; this keeps labels such as the active-alignment selector internationalizable and avoids leaking internal acronyms like “TAL” into product chrome.

Map static JS/CSS should be served with no-store caching in the deploy/testbed path to avoid rapid-deploy version skew while MC code is changing quickly.

### 8.4 Refresh events

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

All customer-data compute tools are asynchronous jobs in v1. Limits protect submission size, queue depth, worker concurrency, transient storage, provider usage, and per-customer fairness. Requests that exceed configured limits fail fast before a job is accepted, with structured guidance where possible.

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

### 14.1 Deploy/test environment

The active EZT MCP deploy/test environment is the ExpertPack droplet:

- Host: `165.245.136.51`
- Public site: `https://expertpack.ai`
- External MCP path: `https://expertpack.ai/mcp/`
- Reverse proxy: nginx `location /mcp/` → `http://127.0.0.1:8100/`
- Existing service lineage: formerly EP MCP testbed; now repurposed as the EZT MCP deploy/test host

The `/mcp` path can be reused for EZT MCP. That means the prior EP MCP service on that path is superseded in this environment unless a separate path is intentionally added later.

The implementation should be forked/derived from the existing EP MCP codebase rather than built as an unrelated server. Reuse the proven FastMCP/Starlette/service structure, auth pattern, config loading, systemd deployment shape, and `/mcp` nginx proxy posture, then add EZT-specific resources/tools on top.

### 14.2 Migration policy

- Use explicit versioned migrations.
- Migrations must be backward-compatible during Azure Container Apps revision rollout.
- Never require downtime for production.
- Reference data updates to `geo` are operational data pipeline tasks, not app migrations.

### 14.3 Container contents

The container image includes:

- Python application code;
- static Map Component build artifacts if served by the app, or asset references if served from blob/CDN;
- schema files and guidance markdown resources;
- no customer data;
- no secrets.

### 14.4 Configuration

Configuration sources:

- local dev: `config.yaml` and/or environment variables;
- production: Azure Key Vault + environment references;
- tests: isolated test config with fake providers and temporary DB.

Config should validate at startup and fail fast when required production secrets or DB connectivity are missing.

Dissolve tuning is config-driven. Current settings:

- `dissolve.simplify_tolerance` / `EZT_MCP_DISSOLVE_SIMPLIFY_TOLERANCE` — detailed geometry simplification; default `0.0` until real map artifacts and acceptable loss are reviewed.
- `dissolve.overview_simplify_tolerance` / `EZT_MCP_DISSOLVE_OVERVIEW_SIMPLIFY_TOLERANCE` — simplified overview geometry; default `0.0`.
- `dissolve.partition_threshold` / `EZT_MCP_DISSOLVE_PARTITION_THRESHOLD` — part count at which the Shapely backend switches to Benton-style two-pass spatial partitioning; default `10000` because local benchmarks show direct GEOS `unary_union` is faster through at least 5k synthetic parts, while the partitioned path is kept available for pathological real-world cases.
- `dissolve.target_parts_per_cluster` / `EZT_MCP_DISSOLVE_TARGET_PARTS_PER_CLUSTER` — target cluster size for partitioned dissolve; default `100`.
- `dissolve.max_clusters` / `EZT_MCP_DISSOLVE_MAX_CLUSTERS` — maximum clusters per union; default `30`.

PostGIS dissolve backend selection is tabled until the Shapely implementation has been exercised with real development data. Sliver buffer cleanup is also tabled and should only be added behind an explicit option if visible artifacts appear during development.

---

## 15. Implementation Sequence

Recommended implementation order:

1. Fork/derive the implementation from the existing EP MCP server skeleton and preserve the proven FastMCP/Starlette deployment shape.
2. Project scaffold and CI gates.
3. Shared models: TS parse/serialize, identity, structured errors.
4. Schema/example validation in CI.
5. Minimal `get_map_visualization` read-only loop for TS/TAL visual verification.
6. DB pool and repositories for part layers, transient cache, async jobs/progress/results, audit log.
7. Job submission/status/result/cancel control plane with customer isolation tests.
8. Direct Build flat path.
9. Direct Build hierarchical path and rollup geometry.
10. Analyze for Direct Build outputs.
11. Realign for leaf moves.
12. `get_map_visualization` select-mode selection/state resources.
13. Ingest Accounts + geocoder cache/provider mocks.
14. Account Build.
15. Auto Build Mode A.
16. Auto Build Mode B.
17. Auto Build Scoped Split.
18. Analysis presentation guidance resources/prompts.
19. Production hardening: auth, Key Vault, observability, limits, deployment manifests.

This sequence intentionally implements a minimal map visualization loop before deeper compute work because visual inspection is the fastest way to catch bad geometry, styling, hierarchy, labels, active TAL selection, and repair side effects. Direct Build remains the first compute path because it exercises the TS/TAL/hierarchy core without requiring account ingestion, geocoding, or optimization algorithms.

---

## 16. Open Technical Questions

These are implementation questions, not product-contract blockers:

1. **Transient cache backend:** PostgreSQL-only for v1 simplicity, or Redis-compatible cache for lower latency and easier TTL eviction?
2. **Geometry backend threshold:** when should dissolve/repair run in Shapely vs PostGIS? Tabled until real dev data shows Shapely's partitioned backend is insufficient.
3. **Auto-build optimizer baseline:** which initial heuristic gives the best balance of quality, explainability, and implementation speed?
4. **Map Component asset hosting:** serve from MCP container for v1 or from blob/CDN from the start?
5. **MCP Tasks adoption timing:** expose native MCP Tasks immediately where client/server support is mature, or ship EZT job resources first and map MCP Tasks onto the same internal job table later?
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
