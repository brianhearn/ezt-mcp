# FUNCTIONAL_SPEC.md — EZT MCP Functional Contract

**Version:** 0.1.2
**Date:** 2026-05-12
**Status:** Draft — open questions resolved for v1 surface

This document defines EZT MCP's externally observable behavior for agent/client implementers. It specifies MCP tools, resources, prompts, caller-visible state rules, validation behavior, and acceptance criteria independent of implementation internals.

This spec must conform to [CONSTITUTION.md](CONSTITUTION.md). Workflow coverage comes from [SCENARIOS.md](SCENARIOS.md). Map Component UX concepts live in [MAP_COMPONENT.md](MAP_COMPONENT.md). Map Component product chrome and visual tokens live in [DESIGN.md](DESIGN.md). Internal implementation design belongs in [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md).

---

## 1. Contract Principles

1. **TS in, TS out for geometry-bearing operations.** Geometry-bearing tools accept a Territory Solution (TS) or short-lived TS handle and return an updated TS or TS handle unless this spec explicitly says otherwise.
2. **Agent owns durable customer state.** EZT MCP never becomes the system of record for account data, territory solutions, or customer alignments.
3. **Build tools append TALs.** Direct Build, Account Build, and Auto Build append a new Territory Alignment Layer (TAL) to the input TS rather than replacing existing TALs.
4. **Realign modifies one named TAL.** Realign requires an explicit `tal_id` whenever a TS contains more than one TAL.
5. **Analyze returns facts, not prose.** Analyze returns structured JSON facts and caveats. Presentation guidance is exposed separately for agents to produce human-facing narratives.
6. **Map sessions are transient coordination.** Map sessions and TS cache handles are short-lived transport/session conveniences, not durable storage.
7. **Failures are structured.** Tools return actionable error codes, row/part-level failure details where practical, and safe user-facing messages. Unhandled exceptions are never exposed as client behavior.
8. **Caller intent stays explicit.** Ambiguous territory, metric, workload, mode, or grouping requests should be surfaced to the agent as clarification-required errors or warnings rather than guessed silently.

---

## Schema Drafts

Initial JSON Schema drafts live in [`schemas/`](schemas/). They cover the common envelope/error types, TS references/identity, `direct_build`, and `auto_build` including Scoped Split. These schemas are draft executable contracts and will expand as the functional surface stabilizes.

## Related UI Contract

[`MAP_COMPONENT.md`](MAP_COMPONENT.md) owns the human-facing map interaction model: view/select modes, selection UX, embedding targets, and browser/session communication at the conceptual level. [`DESIGN.md`](DESIGN.md) owns the visual contract for that component: EZT Designer V2 tokens, map chrome, panels, legends, labels, empty/loading/error states, and hard design constraints.

Functional tool/resource contracts should reference mode, selection, and session behavior from this spec and `MAP_COMPONENT.md`; they should not restate visual rules. Implementation agents building the Map Component must read `DESIGN.md` before writing UI.

## 2. Common Data and Calling Conventions

### 2.1 Territory Solution references

Tools that operate on an existing TS accept one of:

- a full `ts` payload; or
- a `ts_handle` previously returned by EZT MCP.

If both are supplied, the full `ts` is authoritative unless a tool-specific contract says otherwise.

A valid `ts_handle` is customer/API-key scoped, non-guessable, TTL-bound, and safe to miss. Cache miss is normal behavior: the agent should resend the full TS.

### 2.2 TS identity

Every returned TS or TS handle should include identity metadata:

- `ts_id`
- `revision`
- `content_hash`
- `updated_at`

Tools that modify a TS increment or otherwise update the revision and return a new content hash.

### 2.3 Optimistic concurrency

Mutation tools that operate on an existing TS should accept expected identity fields:

- `expected_revision`
- `expected_content_hash`

If the expected identity does not match the supplied/current TS, the tool returns `STALE_TS_REVISION` and does not mutate the TS.

### 2.4 Part layers

Build and realign operations that work from geographic parts require a `part_layer`, such as `us_zips`, `us_counties`, or `ca_fsa`.

EZT MCP validates that referenced part IDs exist in the chosen part layer. Invalid IDs are returned as structured failures and are not silently ignored.

### 2.5 Point layers

Account/location data is represented as one or more TS point layers. All non-geometry input columns should pass through as point feature properties unless explicitly rejected for safety or schema validity.

Point layers may declare metric fields for downstream analysis and build behavior.

### 2.6 Common output envelope

Tool responses should use a consistent shape at the functional level:

- `ok`: boolean
- `result`: tool-specific success payload when `ok=true`
- `error`: structured error payload when `ok=false`
- `warnings`: zero or more non-fatal warnings
- `ts_identity`: returned when a TS is produced, modified, cached, or referenced

Exact JSON Schema will live beside this spec once `schemas/` exists.

### 2.7 Common structured error fields

Errors should include:

- `code`
- `message`
- `details`
- `retryable`
- `user_action_required`

Common error codes include:

| Code | Meaning |
|---|---|
| `INVALID_TS` | TS is malformed or violates required conventions. |
| `INVALID_TS_HANDLE` | Handle is missing, expired, not found, or not scoped to caller. |
| `STALE_TS_REVISION` | Expected revision/hash does not match current TS. |
| `UNKNOWN_PART_LAYER` | Requested part layer is not available. |
| `UNKNOWN_PART_ID` | One or more supplied part IDs do not exist in the part layer. |
| `UNKNOWN_TAL_ID` | Requested TAL does not exist in the TS. |
| `AMBIGUOUS_TAL` | Multiple TALs exist and no explicit target was supplied. |
| `UNKNOWN_POINT_LAYER` | Requested point layer does not exist in the TS. |
| `UNKNOWN_SOURCE_TERRITORY` | Requested source territory for a scoped split or realign operation does not exist. |
| `UNKNOWN_FIELD` | Requested metric/grouping/dwell/frequency field does not exist. |
| `INVALID_FIELD_TYPE` | Field exists but cannot be used for the requested purpose. |
| `CLARIFICATION_REQUIRED` | Request is under-specified and should be clarified by the agent. |
| `UNSUPPORTED_OPERATION` | Request is outside the current functional contract. |
| `PARTIAL_FAILURE` | Some rows/items succeeded and some failed. |
| `PROVIDER_UNAVAILABLE` | External provider dependency is unavailable. |

---

## 3. MCP Tools — v1 Draft Surface

| Tool | Purpose | Primary scenarios |
|---|---|---|
| `geocode_address` | Convert address records into standardized point locations. | GC-001, GC-002 |
| `ingest_accounts` | Create or append a TS point layer from account/location rows. | IA-001 to IA-005, S003 |
| `direct_build` | Build a TAL from explicit part-to-territory assignments. | DB-001 to DB-003 |
| `account_build` | Build a TAL by grouping account points on an attribute. | ACB-001 to ACB-003 |
| `auto_build` | Build a balanced TAL from point layers, workload rules, and optional metric; includes scoped territory-split builds. | AB-001 to AB-016, RL-002, S003 |
| `realign` | Move parts within a specific TAL and return an updated TS. | RL-001, RL-003 to RL-005, S001, MC-004 |
| `analyze` | Return structured analysis facts for one or more TALs or scopes. | AN-001 to AN-005, S001, S003 |
| `map_session_create` | Create a transient read-only or select-mode Map Component session. | MC-001 to MC-004, S001, S002 |

V1 TS cache behavior is implicit. Public tools may accept and return TS handles, but `ts_cache_put` is not a public v1 MCP tool.

---

## 4. Tool Contract: `geocode_address`

### 4.1 User intent

Use when an agent has address-bearing records and needs standardized coordinates before account ingestion or point correction.

### 4.2 Functional input

The tool accepts:

- address records with caller-provided row IDs;
- either one full address string per row or structured address fields;
- optional country/region hints;
- optional geocoding quality threshold;
- optional provider preference only when allowed by policy.

The tool does not require or return a TAL.

### 4.3 Functional behavior

1. Normalize address strings for cache lookup.
2. Use cached geocode results when available and valid.
3. Route uncached geocoding through TomTom Level 1 first, then Azure Maps fallback.
4. Return coordinates, confidence/match metadata, provider metadata, and row-level status.
5. Return partial failures explicitly; do not silently drop rows.
6. Avoid geocoding rows that already contain valid coordinates unless the caller explicitly requests re-geocoding.

### 4.4 Functional output

On success or partial success, returns:

- `geocoded_rows`: row ID, latitude, longitude, confidence, match quality, provider/cache source;
- `failed_rows`: row ID, reason code, message, provider details where safe;
- `summary`: counts for input, geocoded, cached, failed, low-confidence.

### 4.5 Failure behavior

- Bad address rows produce row-level failures.
- Provider outage returns `PROVIDER_UNAVAILABLE` if no rows can be processed.
- Mixed success returns `PARTIAL_FAILURE` with usable successful rows.

### 4.6 Acceptance criteria

- Covers GC-001 and GC-002.
- Existing valid coordinates are not modified unless explicitly requested, supporting GC-003 through agent-side skip or later ingest behavior.
- Every input row is represented in either success or failure output.

---

## 5. Tool Contract: `ingest_accounts`

### 5.1 User intent

Use when an agent has customer account/location rows and needs a TS point layer suitable for build, analysis, map rendering, or later correction.

### 5.2 Functional input

The tool accepts:

- optional existing `ts` or `ts_handle`;
- account/location rows with stable row IDs;
- point layer name and label;
- coordinate fields or address fields;
- optional pre-geocoded output from `geocode_address`;
- optional metric field declarations;
- optional normalized visit-frequency field;
- optional dwell-time field designation.

### 5.3 Functional behavior

1. Preserve all caller-supplied non-geometry columns as point properties unless invalid.
2. Use valid latitude/longitude when present.
3. Geocode only rows that lack valid coordinates and have sufficient address data.
4. Return row-level failures for records that cannot become valid point features.
5. Add a new point layer to the TS or create a new TS if none was supplied.
6. Do not create a TAL.
7. Do not parse raw visit-frequency text; agents must normalize it before passing it as a workload field.

### 5.4 Functional output

Returns:

- updated TS or TS handle;
- TS identity;
- point layer ID/name;
- ingested row count;
- failed row list;
- detected/declared metric fields;
- warnings for missing coordinates, low-confidence geocodes, or ambiguous field types.

### 5.5 Failure behavior

- If some rows fail but at least one valid point is created, return partial success with failures.
- If no rows can be converted into valid points, return `PARTIAL_FAILURE` or `INVALID_FIELD_TYPE` depending on cause and no updated TS.
- If an existing TS is stale, return `STALE_TS_REVISION` when expected identity was supplied.

### 5.6 Acceptance criteria

- Covers IA-001 through IA-005.
- Mixed coordinate/address files produce one point layer with row-level provenance.
- All preserved fields remain available for Direct/Account/Auto Build and Analyze.

---

## 6. Tool Contract: `direct_build`

### 6.1 User intent

Use when Monica already has explicit part-to-territory assignments, usually from Excel, CSV, ERP, CRM, or another planning system.

### 6.2 Functional input

The tool accepts:

- optional existing `ts` or `ts_handle`;
- `part_layer`;
- assignment rows mapping part IDs to a `territory_path` (ordered array of labels from root to leaf, max 5 elements);
- new TAL label;
- optional territory metadata fields;
- optional repair policy flags allowed by this spec.

The `territory_path` replaces the flat `territory_label` field. A single-element path `["FL-01"]` is equivalent to the former flat label — non-hierarchical builds require no structural change from the caller. Multi-element paths such as `["Eastern US", "Southeast Region", "Florida"]` cause the server to materialize rollup nodes automatically.

The agent is responsible for converting Excel, CSV, or JSON from external systems into standard assignment rows before calling the tool. When a source uses pipe-delimited names (e.g., `East|Southeast|FL`), the agent splits on `|` and passes the resulting array as `territory_path`; the tool itself never accepts pipe strings.

### 6.3 Functional behavior

1. Validate the part layer and all supplied part IDs.
2. Derive the territory tree from `territory_path` arrays: leaf nodes are territories with assigned parts; intermediate nodes are rollup territories created automatically.
3. Assign `depth` (0 = root) and `parent_territory_id` to each territory node; set `is_leaf` accordingly.
4. Dissolve leaf parts into leaf territory geometry; dissolve rollup geometry as the union of child geometries, bottom-up.
5. Run Repair for gaps, holes, and contiguity issues on leaf territories according to product rules.
6. Append a new TAL to the input TS or create a new TS when no TS was supplied.
7. Preserve existing point layers and existing TALs.
8. Set `active_tal_id` to the newly appended TAL unless the caller opts out where allowed.

### 6.4 Functional output

Returns:

- updated TS or TS handle;
- TS identity;
- new `tal_id`;
- leaf territory count and total territory count (leaf + rollup);
- assignment summary;
- hierarchy summary (max depth reached, rollup node count);
- repair summary;
- invalid/unmatched part list if partial behavior is allowed.

### 6.5 Failure behavior

- Unknown part layer returns `UNKNOWN_PART_LAYER`.
- Unknown part IDs return `UNKNOWN_PART_ID` with the invalid IDs listed.
- If assignment gaps are repairable, return success with repair warnings.
- If topology cannot be repaired under v1 rules, return structured failure.

### 6.6 Acceptance criteria

- Covers DB-001 through DB-003.
- Direct Build never replaces existing TALs.
- Repair side effects are reported to the caller.

---

## 7. Tool Contract: `account_build`

### 7.1 User intent

Use when territories should be inferred from account ownership or grouping fields such as territory name, manager name, rep name, territory code, or service rep ID.

### 7.2 Functional input

The tool accepts:

- `ts` or `ts_handle` containing at least one point layer;
- point layer ID/name;
- grouping attribute field;
- `part_layer` used to create territory geography;
- new TAL label;
- optional repair policy flags allowed by this spec.

### 7.3 Functional behavior

1. Validate that the point layer and grouping field exist.
2. Treat grouping values as labels, even when they are numeric.
3. Assign parts to groups based on account locations and product rules.
4. Dissolve assigned parts into territories.
5. Run Repair for contiguity and holes.
6. Append the new TAL while preserving existing point layers and TALs.
7. Set `active_tal_id` to the new TAL unless the caller opts out where allowed.

### 7.4 Functional output

Returns:

- updated TS or TS handle;
- TS identity;
- new `tal_id`;
- group/territory count;
- unassigned account summary;
- repair summary;
- warnings for sparse, scattered, or non-contiguous groups.

### 7.5 Failure behavior

- Missing grouping field returns `UNKNOWN_FIELD`.
- Non-usable grouping field returns `INVALID_FIELD_TYPE`.
- Missing/invalid account coordinates return row/account-level failures when practical.
- Repair impossibility returns structured failure with affected groups.

### 7.6 Acceptance criteria

- Covers ACB-001 through ACB-003.
- Numeric grouping codes are never interpreted as metrics.
- Existing TALs are preserved.

---

## 8. Tool Contract: `auto_build`

### 8.1 User intent

Use when Monica wants EZT MCP to create a balanced territory alignment from account points, workload assumptions, an optional metric, and either fixed territory count or fixed workload target.

### 8.2 Functional input

The tool accepts:

- `ts` or `ts_handle` containing a point layer;
- point layer ID/name;
- `part_layer`;
- new TAL label;
- exactly one build mode:
  - Mode A: fixed territory count;
  - Mode B: fixed workload target with closest-to or not-to-exceed variant; or
  - Scoped Split: split one existing territory into two or more balanced replacement territories within a derived TAL;
- optional source `tal_id` and `territory_id` when using Scoped Split;
- resolved dwell-time input when workload is used;
- optional normalized visit-frequency field;
- optional one secondary metric field or synthetic account count metric;
- optional workload/metric bias pair.

The agent is responsible for resolving dwell time and normalizing visit frequency before calling this tool.

### 8.3 Functional behavior

1. Reject requests that combine incompatible build modes.
2. For full-TS builds, append a new TAL built from the selected point layer and part layer.
3. For Scoped Split, derive a new TAL from the source TAL, replace the selected source territory with the newly optimized territories, preserve all other territories from the source TAL, and append the derived TAL to the TS.
4. Use pure workload balance when no metric is named.
5. Use default 50-50 workload/metric bias when a metric is named but no bias is supplied.
6. Support pure metric balance when workload bias is zero and do not require dwell time in that case.
7. Support synthetic account count without requiring an account-count column.
8. Reject multiple secondary metrics.
9. Estimate workload according to Constitution §2.10.
10. Append a new TAL and set it as `active_tal_id`.
11. Preserve existing point layers and existing TALs.

### 8.4 Functional output

Returns:

- updated TS or TS handle;
- TS identity;
- new `tal_id`;
- build mode summary;
- scoped split summary when applicable;
- territory count;
- objective/bias summary;
- workload and metric distribution summary;
- warnings for missing data, outliers, constraint tension, or derived territory count.

### 8.5 Failure behavior

- Mode conflict returns `CLARIFICATION_REQUIRED` or `UNSUPPORTED_OPERATION` with guidance.
- Scoped Split without a source TAL or source territory returns `CLARIFICATION_REQUIRED`.
- Scoped Split with an unknown source territory returns `UNKNOWN_SOURCE_TERRITORY`.
- Missing dwell time for workload build returns `CLARIFICATION_REQUIRED`.
- Unknown metric field returns `UNKNOWN_FIELD`.
- Multiple metrics return `UNSUPPORTED_OPERATION` and should recommend separate TALs.

### 8.6 Acceptance criteria

- Covers AB-001 through AB-016, RL-002, and S003.
- Scoped Split is v1 behavior for customer requests like “split this oversized territory”; it is handled by Auto Build, not Realign.
- Build-time dwell override, per-account dwell column, and session default behavior are caller-visible and explainable.
- Visit frequency is numeric and normalized before EZT MCP consumes it.

---

## 9. Tool Contract: `realign`

### 9.1 User intent

Use when Monica wants to change an existing TAL by moving specific parts between territories, including parts selected visually in the MC or named directly in chat.

### 9.2 Functional input

The tool accepts:

- `ts` or `ts_handle`;
- target `tal_id`;
- `part_layer` when not inferable from the TAL;
- one or more directed part-move operations;
- optional expected TS identity;
- optional `map_session_id` to refresh a live MC session after success.

### 9.3 Functional behavior

1. Validate TS identity when expected revision/hash is supplied.
2. Validate target TAL and part IDs.
3. Validate source/target territories when supplied.
4. Move parts within the target TAL only.
5. Preserve all other TALs.
6. Re-dissolve affected territory geometry.
7. Run Repair when required by product rules.
8. Return repair side effects and changed-territory summary.
9. Notify the map session to refresh when a valid `map_session_id` is supplied.

### 9.4 Functional output

Returns:

- updated TS or TS handle;
- TS identity;
- changed territories;
- moved parts;
- repair summary;
- map refresh status when applicable.

### 9.5 Failure behavior

- Stale TS identity returns `STALE_TS_REVISION` and no mutation.
- Multiple TALs without target returns `AMBIGUOUS_TAL`.
- Invalid parts return `UNKNOWN_PART_ID`.
- Ambiguous natural-language targets should be resolved by the agent before calling Realign.

### 9.6 Acceptance criteria

- Covers RL-001, RL-003, RL-004, RL-005, S001, and MC-004.
- Realign never modifies untargeted TALs.
- Stale map selections are rejected safely.

Territory splitting is intentionally excluded from Realign v1. Use `auto_build` Scoped Split for RL-002.

---

## 10. Tool Contract: `analyze`

### 10.1 User intent

Use when Monica wants objective facts about one TAL, multiple TALs, selected parts, geography-only balance, metric distribution, or likely realignment impact.

### 10.2 Functional input

The tool accepts:

- `ts` or `ts_handle`;
- optional `tal_ids`; default is the active TAL when unambiguous;
- optional `scope`, such as selected part IDs;
- optional metric fields;
- optional comparison request across TALs;
- optional hypothetical move context for impact analysis;
- optional `max_depth`: integer 0–4; when supplied, rollup metrics are returned only up to this depth level (e.g., `max_depth: 1` returns region-level rollups without leaf detail).

### 10.3 Functional behavior

1. Analyze any valid TS from storage; no recent build is required.
2. Analyze one TAL by default when a single active TAL is clear.
3. Compare multiple TALs when requested.
4. Support scoped analysis for selected parts.
5. Support geography-only analysis when no point layers exist.
6. Return structured facts, caveats, and confidence notes.
7. Do not generate polished prose; agents use Analysis Presentation Guidance for that.
8. For hierarchical TALs, compute rollup metrics bottom-up from leaf territories. Return analysis at all depth levels by default, or up to `max_depth` when specified. Leaf-level metrics are always authoritative; rollup metrics are derived sums.

### 10.4 Functional output

Returns structured analysis sections as applicable:

- TS/TAL summary (including hierarchy depth and rollup node count when the TAL is hierarchical);
- balance scores (computed over leaf territories only; rollup balance is not meaningful);
- territory metric distributions, organized by depth level for hierarchical TALs;
- workload distributions;
- outliers and exceptions (leaf territories only);
- scoped selection aggregates;
- cross-TAL comparison;
- caveats and missing-data notes;
- presentation hints or links to guidance resources.

### 10.5 Failure behavior

- Ambiguous TAL target returns `AMBIGUOUS_TAL`.
- Unknown metric or point layer returns structured field errors.
- No point layers is not an error; geography-only analysis should still run where possible.

### 10.6 Acceptance criteria

- Covers AN-001 through AN-005, S001, S002, S003, and MC-005.
- Selection-level analysis is handled through `scope`, not a separate tool.

---

## 11. Tool Contract: `map_session_create`

### 11.1 User intent

Use when an agent needs a temporary MC URL for read-only review, executive sharing, or assisted spatial selection.

### 11.2 Functional input

The tool accepts:

- `ts` or `ts_handle`;
- mode: `view` or `select`;
- optional active `tal_id`; default is TS `active_tal_id` when present;
- optional named presentation view/style context;
- optional expiry duration within policy limits;
- optional allowed interaction flags.

### 11.3 Functional behavior

1. Create a short-lived, customer-scoped map session.
2. Return a browser-safe URL containing only a short-lived map session token or exchange code.
3. Never expose the customer's MCP API key to the browser.
4. In `view` mode, allow map review but no selection commits.
5. In `select` mode, allow local transient selection and committed selection events.
6. Expose subscribable selection and state resources.
7. Support live refresh events after successful Realign when connected.
8. Expire sessions predictably and report expiration through state/resource behavior.

### 11.4 Functional output

Returns:

- `map_session_id`;
- `map_url`;
- `selection_resource_uri` when mode supports selection;
- `state_resource_uri`;
- `expires_at`;
- active TS identity;
- active TAL/mode summary.

### 11.5 Failure behavior

- Missing or invalid TS returns `INVALID_TS` or `INVALID_TS_HANDLE`.
- Ambiguous active TAL returns `AMBIGUOUS_TAL` when a TAL is required for the requested mode/view.
- Unsupported mode returns `UNSUPPORTED_OPERATION`.

### 11.6 Acceptance criteria

- Covers MC-001 through MC-004, S001, and S002.
- Map sessions are transient coordination objects, not durable TS storage.

---

## 12. TS Cache Behavior — implicit v1 surface

TS caching is a transport optimization, not a public v1 MCP tool. Agents should not need to manage cache lifecycle directly.

Functional behavior:

1. Tools may accept either full `ts` payloads or valid `ts_handle` references where appropriate.
2. Tools may return a `ts_handle` for large TS payloads or sequential workflows.
3. Handles are short-lived, customer/API-key scoped, non-guessable, and safe to miss.
4. Cache miss returns `INVALID_TS_HANDLE`; the agent resends the full TS.
5. No cache handle is durable customer storage or a system-of-record reference.

Acceptance criteria:

- Covers CH-001 and CH-002.
- There is no public v1 `ts_cache_put` tool.
- Cache behavior never changes the TS-in/TS-out functional model.

---

## 13. MCP Resources — v1 Draft Surface

### 13.1 `ezt://map-sessions/{map_session_id}/selection`

Represents the latest committed selection from a select-mode MC session.

Functional behavior:

- Updated only when Monica explicitly commits a selection, e.g. clicks Done.
- Carries awareness-level selection data, not full metric analysis.
- Triggers MCP resource notifications to subscribed agents when changed.
- Expires with the map session.

Expected data includes:

- map session ID;
- event ID and timestamp;
- TS identity at selection time;
- active TAL;
- part layer;
- selected part IDs;
- selection method;
- selected count;
- current assignment summary when cheaply available.

The agent should call `analyze` for authoritative account counts, sales volume, workload, and move impact.

### 13.2 `ezt://map-sessions/{map_session_id}/state`

Represents current transient map session state.

Expected data includes:

- map session ID;
- mode;
- active TAL;
- active TS identity;
- expiry;
- last selection status;
- last refresh status;
- session state such as active, expired, or revoked.

---

## 14. MCP Prompts / Guidance Resources — v1 Draft Surface

### 14.1 Analysis Presentation Guidance

EZT MCP should expose versioned guidance that teaches agents how to turn `analyze` output into useful human-facing insight.

Functional behavior:

- Guidance is separate from `analyze` facts.
- Guidance should support at least executive summary, territory designer diagnostic, sales manager action list, and QA/verification styles.
- Guidance should include caveat language for missing metrics, geography-only analysis, stale data, and repair side effects.

Future owning document: `ANALYSIS_DESIGN.md`.

### 14.2 Territory Design Guidance

EZT MCP may expose prompts/resources for territory-design interpretation and agent UX choices.

Functional behavior:

- Help agents explain workload/metric tradeoffs.
- Help agents ask concise clarification questions.
- Help agents interpret repair warnings and analysis caveats.
- Never override structured tool facts.

---

## 15. Resolved v1 Scope Decisions

1. **Territory split is v1 via Auto Build.** Customer requests like “split this oversized territory” are common and belong in v1. The contract is `auto_build` Scoped Split: derive a new TAL from the source TAL, replace one source territory with two or more optimized territories, and preserve the rest of the source TAL. It is not part of `realign` v1.
2. **TS cache is implicit.** Public tools may accept/return TS handles, but `ts_cache_put` is not a public v1 MCP tool. Cache miss is expected and recoverable by resending the full TS.
3. **Map sessions are v1.** `map_session_create` is part of the public v1 MCP tool set with `view` and `select` modes. Browser URL / OpenClaw Canvas is v1; Teams and Power BI embedding are post-MVP.
4. **Schemas start before implementation.** Add `schemas/` after this functional surface stabilizes and before implementation begins. JSON Schema owns exact structure; this Functional Spec owns behavior.
5. **Exports and Power BI are post-MVP.** V1 sharing is read-only MC browser URL plus Analyze-backed narrative. Formal Power BI/export contracts are deferred.
6. **Point Location Update is post-MVP.** PLU-001 remains a future scenario. Phase 1 handles corrected locations through re-ingestion or point-layer replacement by the agent workflow.

---

## 16. Acceptance Coverage Checklist

| Scenario group | Covered by |
|---|---|
| S001 | `map_session_create`, selection resource, `analyze`, `realign` |
| S002 | `map_session_create`, `analyze`, presentation guidance |
| S003 | `ingest_accounts`, `auto_build`, `analyze`, MC TAL switching |
| GC-001 to GC-003 | `geocode_address`, `ingest_accounts` |
| IA-001 to IA-005 | `ingest_accounts` |
| DB-001 to DB-003 | `direct_build` |
| ACB-001 to ACB-003 | `account_build` |
| AB-001 to AB-016 | `auto_build` |
| RL-001, RL-003 to RL-005 | `realign` |
| RL-002 | `auto_build` Scoped Split |
| AN-001 to AN-005 | `analyze`, presentation guidance |
| MC-001 to MC-004 | `map_session_create`, resources |
| MC-005 | `analyze`, presentation guidance |
| CH-001 to CH-002 | Implicit TS handles / cache behavior |
| PLU-001 | Future tool, not Phase 1 |

---

*This functional contract draft has the v1 public surface decisions resolved. Prefer moving next into executable schemas before implementation.*
