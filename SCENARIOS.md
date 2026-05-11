# SCENARIOS.md — EZT MCP Workflow Scenarios

**Version:** 0.8.0
**Date:** 2026-05-11
**Status:** Scenario collection — draft

This document collects concrete human/agent/EZT MCP scenarios before the Functional Spec is finalized. The goal is to stress-test the product architecture against realistic workflows, especially where natural language, map interaction, TS state, MCP tools, resources, and notifications intersect.

Scenarios should be written from the user's perspective first, then mapped to the proposed architecture. As this file grows, it should help validate tool boundaries, resource contracts, notification behavior, TS revision handling, Map Component responsibilities, and agent orchestration patterns.

## Key Terms

Abbreviations used throughout this document. Full definitions in [CONSTITUTION.md §4.1](CONSTITUTION.md).

| Abbreviation | Full Term | Short Definition |
|---|---|---|
| **TS** | Territory Solution | A GeoJSON FeatureCollection — the universal EZT MCP geometry artifact. Contains 0-N point location layers and 0-N TALs, plus solution-level metadata. |
| **TAL** | Territory Alignment Layer | One named territory arrangement inside a TS (e.g. "By Revenue Q1"). A TS can hold multiple TALs for side-by-side comparison. |
| **MC** | Map Component | The browser-based map surface embedded in the agent host. Renders TS geometry over PMTiles basemap/part layers. Supports `view`, `select` modes. |
| **MV** | Map Visual / Map Component | Used interchangeably with MC in older notes; refers to the same Map Component surface. |
| **MCP** | Model Context Protocol | The open protocol (Anthropic/standard) used for tool, resource, and prompt communication between the agent and EZT MCP Server. |
| **EP** | ExpertPack | Structured domain knowledge pack backing EZT MCP's `ep_search` knowledge retrieval surface. |
| **T** | Territory | A single named geographic area within a TAL — the dissolved union of one or more parts (e.g. ZIP codes). |
| **P / Part** | Part | The atomic geographic unit (e.g. one ZIP code polygon) from which territories are composed. |

---

## Scenario Template

Each scenario should eventually include:

- **Actors** — human user, agent, EZT MCP, Map Component, external systems
- **Starting state** — TS/TAL/account data/session assumptions
- **User intent** — what the human is trying to accomplish
- **Happy path** — step-by-step interaction
- **Expected agent behavior** — what the agent should say/do
- **EZT MCP capabilities exercised** — tools/resources/prompts involved
- **Map Component behavior** — render/select/refresh expectations
- **State and identity concerns** — TS revision/hash, active TAL, cache handle, map session state
- **Failure/edge cases** — stale map, expired session, ambiguous instruction, invalid part IDs, metric gaps
- **Open design questions** — unresolved architecture or product decisions

---

## Scenario 001 — Monica selects ZIPs along a territory boundary and realigns them

### Summary

Monica asks her agent to open yesterday's Territory Solution with an active Territory Alignment Layer. The agent opens a live Map Component session. Monica selects several ZIP codes along a territory boundary, clicks Done, reviews account/sales-volume impact, then asks the agent to move the selected ZIPs from Territory 1 to Territory 2. EZT MCP updates the TS and refreshes the Map Component.

### Actors

- **Monica** — territory designer using an agent-assisted workflow
- **Agent** — MCP-capable assistant, e.g. OpenClaw
- **EZT MCP Server** — territory compute, knowledge, map-session coordination, MCP tools/resources/prompts
- **Map Component / Map Visual** — browser-based spatial I/O surface using MapLibre/PMTiles and TS overlays
- **Customer storage** — external system where Monica/customer's durable TS is stored; owned by the agent/customer workflow, not EZT MCP

### Starting state

- A TS from yesterday exists in Monica/customer storage.
- The TS contains at least one TAL.
- The TS has identity metadata:
  - `ts_id`
  - `revision`
  - `content_hash`
  - `updated_at`
- The relevant TAL has a stable `tal_id`; it may already be the TS `active_tal_id`.
- The TAL uses ZIP codes as its part layer, e.g. `us_zips`.
- The TS includes point/account data with at least one business metric such as sales volume, revenue, workload, account count, or similar.
- OpenClaw or another MCP host supports MCP Resource Subscriptions.

### User intent

Monica wants to make a targeted boundary adjustment based on visual inspection, not a broad auto-rebuild. She can identify the ZIPs spatially but does not want to manually list ZIP IDs in chat.

### Happy path

1. Monica tells her agent: “Open yesterday's territory solution that has a TAL.”
2. The agent retrieves the TS from Monica/customer storage.
3. The agent confirms or infers the active TAL.
4. The agent calls a map-session creation capability, e.g. `map_session_create`, with:
   - TS or TS handle
   - `active_tal_id`
   - `mode = select`
   - optional part layer / presentation view
5. EZT MCP creates a short-lived map session and returns:
   - `map_session_id`
   - `map_url`
   - `selection_resource_uri`
   - `state_resource_uri`
   - `expires_at`
6. The agent subscribes to the selection resource through MCP Resource Subscriptions.
7. The agent opens or embeds the `map_url` in the agent host, e.g. OpenClaw Canvas, or provides a link if embedding is unavailable.
8. The Map Component renders:
   - basemap PMTiles
   - ZIP/part-layer PMTiles for hit-testing
   - TS GeoJSON overlay for the active TAL and point layers
   - current territory styling and labels from TS presentation metadata or defaults
9. Monica pans/zooms and selects several ZIP codes along a boundary using click, ctrl-click, lasso, or box selection.
10. The Map Component maintains selection as local transient UI state while Monica edits.
11. Monica clicks **Done**.
12. The Map Component posts a `selection.committed` event to EZT MCP using a short-lived browser map-session token, not the customer's MCP API key.
13. EZT MCP validates the map session, selected part IDs, active TAL, TS revision/hash, and selection payload.
14. EZT MCP updates the map-session selection resource.
15. EZT MCP emits an MCP resource notification to subscribed clients.
16. The agent receives a notification equivalent to: “Monica selected ZIPs 32309, 32308, 32312 from T1.”
17. The agent retrieves or injects relevant territory-alignment guidance from EZT MCP knowledge resources, e.g. `ep_search` or an analysis/realignment prompt/resource.
18. The agent calls Analyze with selection scope:

```json
{
  "tal_ids": ["tal_revenue"],
  "scope": {
    "type": "part_ids",
    "part_layer": "us_zips",
    "part_ids": ["32309", "32308", "32312"]
  }
}
```

19. EZT MCP returns authoritative structured analysis for the selection, including account count, sales volume, current assignment, and likely impact if moved.
20. The agent presents Monica a compact analysis grid showing:
   - selected ZIPs
   - current territory assignment
   - account count
   - sales volume / revenue / relevant metrics
   - potential impact on T1 and T2
   - caveats or warnings
21. Monica is satisfied and says: “Move those from T1 to T2.”
22. The agent calls Realign with:
   - TS or TS handle
   - `tal_id`
   - `part_ids[]`
   - `from_territory_id = T1`
   - `to_territory_id = T2`
   - `expected_revision`
   - `expected_content_hash`
   - optional `map_session_id` for live refresh
23. EZT MCP validates the request, checks optimistic concurrency, reassigns the ZIPs, re-dissolves affected territories, applies Repair if needed, and returns an updated TS or TS handle with updated identity metadata.
24. EZT MCP emits a map-session refresh event such as `ts.updated`.
25. The Map Component receives the refresh event over SSE/WebSocket and re-renders the updated TAL.
26. The agent persists the updated TS back to Monica/customer storage.
27. The agent confirms the realignment and summarizes the resulting metric impact.

### Expected agent behavior

The agent should:

- Retrieve the TS from customer-controlled storage, not ask EZT MCP to fetch durable customer state.
- Create the live map session and subscribe to selection updates.
- Avoid asking Monica to manually type ZIP codes once she has selected them visually.
- Treat the selection notification as awareness, not as authoritative analysis.
- Call Analyze for selection-level metrics.
- Use EZT MCP knowledge guidance to interpret the move and surface meaningful caveats.
- Ask for clarification if Monica says “move those” but the source or target territory is ambiguous.
- Use optimistic concurrency when calling Realign.
- Persist the updated TS after Realign succeeds.

### EZT MCP capabilities exercised

Candidate tool/resource/prompt surfaces:

- `map_session_create` — create short-lived live map session
- `ezt://map-sessions/{id}/selection` — subscribable MCP resource for committed selections
- `ezt://map-sessions/{id}/state` — subscribable/readable resource for map session state
- `analyze_territory_solution` with optional `scope`
- `realign_territory_solution` with optional `map_session_id` refresh behavior
- `ep_search` or equivalent ExpertPack-backed prompt/resource for realignment guidance
- Analysis Presentation Guidance resource/prompt for formatting the selection impact clearly

### Map Component behavior

The Map Component should:

- Render the active TAL and point layers from TS.
- Use PMTiles for basemap and part-layer hit-testing.
- Keep in-progress selection local until Monica clicks Done.
- Emit only committed selection events to EZT MCP.
- Never receive the customer's MCP API key.
- Use a short-lived map-session token or exchange code.
- Include TS identity/revision/hash and active TAL in selection commits.
- Listen for `ts.updated`, `mode.changed`, and `session.expired` events.
- Refresh after successful Realign.

### State and identity concerns

Selection commits should include:

```json
{
  "event_id": "evt_01J...",
  "idempotency_key": "...",
  "event_type": "selection.committed",
  "map_session_id": "ms_01J...",
  "ts_id": "ts_01HX...",
  "ts_revision": 7,
  "content_hash": "sha256:...",
  "active_tal_id": "tal_revenue",
  "part_layer": "us_zips",
  "part_id_property": "zip",
  "part_ids": ["32309", "32308", "32312"],
  "selection_method": "lasso",
  "selected_count": 3
}
```

Realign should accept `expected_revision` and/or `expected_content_hash` so stale selections can be rejected safely.

### Failure and edge cases

- **Expired map session:** agent creates a fresh map session from its current TS.
- **Stale selection:** Realign rejects if TS revision/hash no longer matches; agent refreshes MV and asks Monica to reconfirm.
- **Ambiguous target:** Monica says “move those over” without specifying T2; agent asks a concise clarification or infers only if visually/currently obvious.
- **Invalid part IDs:** EZT MCP rejects with structured errors identifying unmatched/invalid IDs.
- **Mixed current assignments:** selected ZIPs span multiple source territories; agent highlights that before moving.
- **Metric gaps:** selected accounts lack sales volume or account metrics; Analyze returns caveats and agent surfaces them.
- **Repair side effects:** Realign triggers hole-filling or contiguity repair that affects additional ZIPs; agent must report those side effects before or after commit depending on Realign contract.
- **MV network retry/double submit:** `event_id` / `idempotency_key` prevents duplicate selection commits.
- **PMTiles unavailable:** Map may render TS but selection mode is disabled or degraded.
- **Customer storage persist failure:** Realign succeeded but agent cannot save updated TS; agent must warn Monica and preserve/retry the updated output.

### Design conclusions from this scenario

1. **Map sessions should be first-class.** They are transient coordination objects, not durable customer storage.
2. **Selection should be an explicit commit.** The agent should be notified when Monica clicks Done, not on every map interaction.
3. **Analyze should support scoped analysis.** Prefer extending Analyze with `scope` over creating a separate `analyze_selection` tool.
4. **Notifications should be lightweight.** Resource notifications should identify the selection; Analyze should produce authoritative metrics.
5. **Realign should support optimistic concurrency.** Use TS revision/hash to avoid applying stale selections.
6. **MV refresh should be event-driven.** Realign should be able to trigger a map-session refresh event.
7. **Browser tokens must be constrained.** The Map Component should receive only a short-lived map-session token, never customer MCP credentials.
8. **Server/agent enriches business meaning.** PMTiles are display/hit-test artifacts; TS/PostGIS/Analyze are authoritative for assignments and metrics.
9. **Selection events need idempotency.** Retries and double-clicks should not create duplicate agent notifications.
10. **Workflow state should be testable.** Useful states: `created`, `rendered`, `selecting`, `selection_committed`, `analysis_presented`, `realign_requested`, `realigned`, `refreshed`, `expired`.

### Open design questions

- Is `map_session_create` an MVP MCP tool or part of a separate map/share surface?
- Exact naming of map-session resources and event types.
- Whether the agent should subscribe only to selection or also to state/refresh resources.
- Whether OpenClaw Canvas should additionally use direct `postMessage` for local UX while MCP Resource Subscriptions remain authoritative.
- How much current-assignment enrichment should happen at selection commit time versus during Analyze.
- Whether Realign should dry-run repair/side effects before commit when selected parts create topology problems.

---

## Scenario 002 — Monica emails a read-only latest East Coast TS view to her boss

### Summary

Monica opens the latest East Coast Territory Solution, then asks her agent to email the latest view to her boss. The agent uses EZT MCP guidance and map-sharing capabilities to create a temporary read-only Map Component link showing the latest TAL, then sends that link by email with a concise executive summary.

This scenario exercises the quick-review sharing path. It is not a screenshot workflow and not yet the formal Power BI reporting path. It should feel like: “Here is the current plan; open this secure temporary link to review the latest territory map.”

### Actors

- **Monica** — territory designer
- **Monica's boss** — executive/sales leader reviewing the latest alignment
- **Agent** — MCP-capable assistant, e.g. OpenClaw, with access to Monica's customer storage and email capability
- **EZT MCP Server** — territory knowledge, sharing guidance, and temporary Map Component session creation
- **Map Component / Map Visual** — read-only browser map view
- **Customer storage** — durable TS source of truth owned by Monica/customer workflow
- **Email system** — external delivery channel used by the agent after Monica authorizes sending

### Starting state

- A latest East Coast TS exists in Monica/customer storage.
- The TS contains one or more TALs.
- The latest TAL is either:
  - identified by `active_tal_id`, or
  - inferable from TAL metadata such as label, timestamp, revision, or user instruction.
- The TS has identity metadata: `ts_id`, `revision`, `content_hash`, `updated_at`.
- Monica's boss is known in Monica's directory/contact context, or the agent can ask Monica for the recipient.
- The agent has permission to send email only after Monica's explicit instruction/confirmation.

### User intent

Monica wants her boss to review the current East Coast alignment without becoming an editor, installing Designer, or receiving a raw GeoJSON file. She wants a lightweight executive-facing map link.

### Happy path

1. Monica tells her agent: “Open the latest TS for East Coast.”
2. The agent retrieves the latest East Coast TS from Monica/customer storage.
3. The agent identifies the latest TAL and sets or confirms it as the active TAL.
4. Monica reviews it briefly in the agent session or trusts the latest TS.
5. Monica says: “Email the latest to my boss.”
6. The agent determines that this is a sharing workflow, not a realignment workflow.
7. The agent retrieves EZT MCP sharing guidance. Preferred product surface:
   - a deterministic MCP prompt/resource such as `ezt://guidance/sharing/map-view` or `share_map_view_prompt`
   - `ep_search` may support broader guidance, but the exact share workflow should come from versioned EZT MCP resources/prompts rather than ad hoc retrieval alone.
8. The guidance tells the agent how to create a view-only Map Component session for executive review.
9. The agent calls a sharing/map-session capability, e.g. `share_map_view` or `map_session_create`, with:
   - TS or TS handle
   - `tal_id` / `active_tal_id`
   - `mode = view`
   - `audience = executive_review`
   - optional expiration, e.g. 24 hours or 7 days depending customer policy
   - optional presentation preset, e.g. `executive_review`
10. EZT MCP creates a temporary read-only map session and returns:
    - `map_url`
    - `share_id` or `map_session_id`
    - `expires_at`
    - `active_tal_id`
    - optional `summary_resource_uri`
11. The agent optionally calls Analyze for the active TAL to generate a concise executive summary.
12. The agent drafts an email with:
    - short context
    - temporary read-only map link
    - expiration note
    - latest TAL label/date/revision
    - 3-5 bullet summary from Analyze, if available
13. If needed, the agent asks Monica to confirm the recipient and draft before sending.
14. Monica confirms.
15. The agent sends the email to Monica's boss.
16. The agent confirms to Monica that the link was sent and states when it expires.

### Expected agent behavior

The agent should:

- Treat this as **read-only sharing**, not selection/editing.
- Retrieve the TS from customer-controlled storage.
- Prefer EZT MCP's versioned sharing guidance/prompt/resource for exact workflow steps.
- Use `ep_search` only as supplementary knowledge, not the sole source of procedural tool instructions.
- Create a read-only Map Component view, not a screenshot.
- Avoid attaching raw TS/GeoJSON unless Monica explicitly asks.
- Include a short executive summary when useful.
- Respect external-action safety: sending email is an external action, so the agent should have clear user instruction and, where appropriate, confirm recipient/content.
- Mention expiration and read-only status in the email.

### EZT MCP capabilities exercised

Candidate tool/resource/prompt surfaces:

- `share_map_view` — create temporary read-only Map Component share link, or
- `map_session_create` with `mode = view` and `audience = executive_review`
- `ezt://guidance/sharing/map-view` — deterministic sharing workflow guidance resource
- `share_map_view_prompt` — prompt that teaches the agent how to package the link and summary for a given audience
- `analyze_territory_solution` — optional, to generate executive summary facts
- Analysis Presentation Guidance — optional, to format the boss-facing summary

### Map Component behavior

The read-only Map Component should:

- Render the selected/latest TAL clearly.
- Display the TAL label, TS name, revision/date, and expiration context.
- Disable selection and editing tools.
- Provide executive-friendly legend and layer toggles.
- Use an `executive_review` presentation preset where available.
- Avoid exposing raw customer data beyond what the share policy permits.

### State and identity concerns

The share/map session should record:

```json
{
  "share_id": "share_01J...",
  "map_session_id": "ms_01J...",
  "mode": "view",
  "audience": "executive_review",
  "ts_id": "ts_01HX...",
  "ts_revision": 12,
  "content_hash": "sha256:...",
  "active_tal_id": "tal_east_latest",
  "expires_at": "2026-05-12T15:42:00Z"
}
```

The share link should be temporary and scoped. It should not make EZT MCP the durable TS owner.

### Failure and edge cases

- **Latest TAL ambiguous:** multiple candidate TALs appear latest; agent asks Monica which one to share.
- **Boss recipient unknown:** agent asks for email/contact.
- **Email content requires confirmation:** agent drafts and asks Monica before sending if policy/context requires.
- **Share link creation fails:** agent offers fallback export options, but should not default to screenshots as the product path.
- **Expired link:** boss opens after expiration; agent can create a fresh read-only link from the saved TS.
- **Sensitive account details:** executive view may need summary metrics but not account-level points; share policy/preset should control this.
- **Need formal recurring reporting:** agent should suggest Power BI export/reporting path rather than repeated temporary links.

### Design conclusions from this scenario

1. **Read-only Map Component sharing is the quick-review path.** It should replace “open and screenshot” as the official ad hoc review workflow.
2. **Power BI remains the formal reporting path.** For recurring executive dashboards, slicers, refresh cadence, and governance, EZT MCP should feed the existing EasyTerritory Power BI visual/reporting flow.
3. **GeoJSON/table export is the interoperability path.** Useful for external tools, but not the primary executive UX.
4. **Sharing guidance should be deterministic.** Tool-use instructions should live in EZT MCP prompts/resources, not depend only on `ep_search` retrieval.
5. **Share links are transient projections.** They do not change the agent-owned/customer-owned TS source of truth.
6. **External sending remains agent-host responsibility.** EZT MCP creates the secure view/share artifact; the agent handles email according to its host's safety and permission model.

### Open design questions

- Should the MVP expose a distinct `share_map_view` tool, or reuse `map_session_create(mode=view, audience=executive_review)`?
- What default expiration should executive review links use?
- Should share links require recipient identity/auth, or is possession of a short-lived unguessable URL sufficient for v1?
- Which fields/point layers are allowed in an executive view by default?
- Should EZT MCP generate the boss-facing summary directly, or only provide Analyze facts plus presentation guidance?
- How should the Power BI export path be represented in MCP: tool, prompt-guided workflow, or both?

---




## Scenario 003 — Monica pulls CRM accounts and auto-builds two TALs for side-by-side comparison

### Summary

Monica asks her agent to pull the latest accounts from CRM with specific columns including sales figures and store counts. She asks it to build two 10-territory TALs: one balancing workload against store count (50-50 bias), one balancing workload against sales volume (50-50 bias). The agent ingests the accounts (geocoding only what needs geocoding), confirms dwell time, runs both builds sequentially, and presents a comparative analysis — as a styled HTML grid and optionally an interactive map — so Monica can decide which alignment to keep.

### Actors

- **Monica** — territory designer looking to rebuild territories from fresh CRM data
- **Agent** — MCP-capable assistant with CRM tool access and EZT MCP connection
- **CRM system** — customer's CRM (e.g. Dynamics 365), accessible via agent tools or connector
- **EZT MCP Server** — account ingestion, selective geocoding, workload estimation, Auto Build, Analyze, and knowledge resources
- **Customer storage** — where the final TS is persisted; agent-owned, not EZT MCP

### Starting state

- Monica has no existing TS for this project (fresh build).
- The CRM has current account records. Some rows have `lat`/`lon` already populated; others have only address fields.
- Account data does not include a dwell time column. Monica will need to supply a default.
- Monica has specified the columns to pull: account name, address fields, `lat`, `lon`, `store_count`, `sales_volume`.
- EZT MCP has `us_postal` as a supported part layer for this geography.
- Monica wants 10 territories across the continental US.

### User intent

Monica wants to rebuild territories from fresh CRM data. She wants two candidate TALs — one that weights store count alongside workload, one that weights sales volume alongside workload — so she can evaluate the tradeoffs before committing to a direction. She expects the agent to handle geocoding and raise any data quality issues before building.

### Happy path

1. Monica tells her agent: "Pull the latest accounts from CRM — I need account name, address, lat, lon, store count, and sales volume."
2. The agent queries the CRM and retrieves 847 account records with the requested columns. Some rows have `lat`/`lon` populated; others do not.
3. The agent calls `ingest_accounts` on the full record set:
   - All requested columns pass through as point layer properties on the TS — EZT MCP does not filter or interpret them.
   - Rows with valid `lat`/`lon`: coordinate-snapped directly to their containing `part_id` — no geocode call made.
   - Rows missing `lat`/`lon` (or with invalid/out-of-layer coordinates): geocoded using TomTom → Azure Maps fallback; resolved `lat`, `lon`, and `part_id` written back as properties.
   - EZT MCP returns a TS (`revision = 1`) with a point location layer and a structured ingestion report:
     - `total`: 847, `used_coordinates`: 612, `geocoded`: 229, `geocode_failures`: 6 (structured list with account identifiers and failure reasons)
4. The agent reports: "Ingested 847 accounts. 612 used existing coordinates, 229 were geocoded, 6 failed (listed below). Ready to build?"
5. Monica says: "Yes — two TALs, 10 territories. One balancing workload and store count equally, one balancing workload and sales volume equally."
6. The agent recognizes workload is required and that no dwell time column exists in the data. It asks: "I don't see a dwell time column in your accounts. What's a typical visit duration? I'll use that as the default."
7. Monica says: "About 45 minutes."
8. The agent calls `auto_build_territory_solution` for the store-count TAL:

```json
{
  "ts": "<ts_handle or inline TS (revision 1)>",
  "part_layer": "us_postal",
  "territory_count": 10,
  "tal_label": "Workload + Store Count",
  "workload": {
    "dwell_time_minutes": 45
  },
  "metric": {
    "column": "store_count",
    "workload_bias": 50,
    "metric_bias": 50
  }
}
```

   - EZT MCP estimates travel time statistically from account coordinates, computes workload per account using 45-minute dwell, aggregates both workload and `store_count` to the ZIP level, and runs the Auto Build algorithm balancing the two objectives at equal weight.
   - Appends TAL `tal_workload_store` to the TS. Returns updated TS: `revision = 2`, `active_tal_id = tal_workload_store`.

9. The agent calls `auto_build_territory_solution` for the sales-volume TAL on the updated TS:

```json
{
  "ts": "<ts_handle or inline TS (revision 2)>",
  "part_layer": "us_postal",
  "territory_count": 10,
  "tal_label": "Workload + Sales Volume",
  "workload": {
    "dwell_time_minutes": 45
  },
  "metric": {
    "column": "sales_volume",
    "workload_bias": 50,
    "metric_bias": 50
  }
}
```

   - EZT MCP aggregates workload and `sales_volume` to the ZIP level and builds the second TAL.
   - Appends TAL `tal_workload_sales`. Returns updated TS: `revision = 3`, `active_tal_id = tal_workload_store` (unchanged).

10. The agent calls `analyze_territory_solution` with both TAL IDs:

```json
{
  "ts": "<ts_handle or inline TS (revision 3)>",
  "tal_ids": ["tal_workload_store", "tal_workload_sales"],
  "metrics": ["workload_hours", "store_count", "sales_volume"]
}
```

11. EZT MCP returns structured comparative analysis:
    - Per-TAL summary: territory count; mean/min/max/std dev for workload (hours), store count, and sales volume per territory.
    - Per-territory breakdown for each TAL: territory label, estimated workload, store count, sales volume, account count.
    - Balance scores (e.g. coefficient of variation) per TAL per metric.
    - Contiguity and compactness scores per TAL.
    - Caveats: 6 accounts excluded (geocode failures), workload is a statistical estimate (±10–20% vs routed itinerary), null metric values excluded with counts.

12. The agent presents Monica the comparison. Two output modes, offered together or on request:

    **Mode A — Styled HTML grid (default, immediate):**
    - Side-by-side table: rows = territories 1–10, columns = TAL × metric combinations.
    - Summary row: balance CV score, std dev, compactness.
    - Narrative above the table: "Both TALs have similar workload balance. The Store Count TAL gives more even store distribution (CV 0.09 vs 0.18); the Sales Volume TAL gives more even revenue distribution (CV 0.11 vs 0.24). Neither perfectly achieves both because the objectives create tension — territories with many low-revenue stores pull differently from territories with fewer high-revenue accounts. 6 accounts excluded from both builds."
    - Rendered inline in the agent host (e.g. OpenClaw Canvas embed) or offered as a downloadable artifact.

    **Mode B — Interactive map (on request):**
    - Agent calls `map_session_create` with `mode = view`, both TALs available via TAL switcher.
    - Monica toggles between `Workload + Store Count` and `Workload + Sales Volume`.
    - Per-territory labels show workload estimate + primary metric value.

13. Monica reviews and says: "Keep the sales volume one. Save it."
14. The agent optionally drops `tal_workload_store` from the TS, then persists the final TS to customer storage.
15. The agent confirms: "Saved. 10 territories balanced on workload and sales volume (50-50), covering 841 accounts. Workload estimates are ±10–20% — you can refine with detailed routing once you're happy with the alignment."

### Expected agent behavior

The agent should:

- Pull exactly the columns Monica specifies; all columns pass through to the TS point layer without filtering.
- Detect when workload is required but no dwell time column is present; ask Monica for a default before building.
- Call `ingest_accounts` with the full record set; EZT MCP handles per-row coordinate vs. geocode routing.
- Report the ingestion split (used coordinates / geocoded / failed) before building.
- Run both Auto Build calls sequentially — the second depends on the first's TS output.
- Use Analyze for the comparison; do not hand-calculate summaries.
- Present the HTML grid comparison immediately; offer the map on request or proactively if the host supports it.
- Surface the workload estimate caveat (±10–20%) without alarming Monica — it's normal and expected at the planning stage.
- Frame the metric tension honestly: explain why neither TAL achieves perfect balance on both dimensions.
- Ask Monica to choose before persisting the final TS.
- Optionally drop the unused TAL; do not require it as a save precondition.

### EZT MCP capabilities exercised

Candidate tool/resource/prompt surfaces:

- `ingest_accounts` — full account record set in; all columns as point layer properties; selective geocoding; structured ingestion report out
- `auto_build_territory_solution` — workload estimation + optional single metric, bias-weighted TAL build, appended to TS; called twice sequentially
- `analyze_territory_solution` with `tal_ids[]` and `metrics[]` — multi-TAL comparative analysis including workload
- Analysis Presentation Guidance resource/prompt — styled HTML grid rendering rules; narrative framing for workload/metric tradeoff explanation
- `map_session_create` with multi-TAL TS, `mode = view`, TAL switcher enabled
- `drop_tal` (or equivalent) — optional cleanup before final persist
- `ep_search` — optional: caveats on workload estimation accuracy, metric tension, bias selection guidance

### Map Component behavior

The Map Component should:

- Render the active TAL on load.
- Expose a TAL switcher when the TS contains multiple TALs (labels from `tal_label`).
- Switch TALs without a full page reload; re-render territory layer from TS GeoJSON.
- Show per-territory metric labels (workload hours + primary metric) using TS presentation metadata or defaults.
- In `view` mode: no selection, no editing. TAL switching is the only interactive surface.
- Display active TAL label and revision/date in map chrome.

### State and identity concerns

- The TS grows through three revisions: ingest (rev 1), first Auto Build (rev 2), second Auto Build (rev 3).
- Each Auto Build call must pass the current TS or handle at the correct revision; stale handles produce a clear revision-mismatch rejection.
- The agent tracks `ts_id` and `revision` throughout; must not cache a stale handle across sequential builds.
- Geocode failures are informational; partial success does not block the build unless Monica cancels.
- The final persisted TS should reflect the chosen TAL and any cleanup, with a clean `revision` and `content_hash`.

### Failure and edge cases

- **CRM query fails:** agent cannot proceed; surfaces error and suggests retry or manual data paste.
- **All rows have coordinates:** `ingest_accounts` skips geocoding entirely — pure coordinate-snap + part-ID lookup pass.
- **Some coordinates are invalid or out-of-layer:** treated as geocode-required, not silently snapped to nearest part; included in the failure list with reason.
- **High geocode failure rate (>10%):** agent pauses and asks Monica to confirm before building on partial data.
- **Dwell time column present in data:** agent passes `dwell_time_column: "avg_visit_duration"` instead of a scalar default; EZT MCP uses per-account values.
- **Monica sets `workload_bias=0`:** pure metric balance; dwell time is not required; agent should not ask for it.
- **`balance_column` has many nulls:** EZT MCP excludes null-metric accounts from aggregation and reports the exclusion count; agent surfaces caveat before building.
- **Monica asks to "balance on both store count and sales volume at once":** agent explains EZT MCP v1 supports one secondary metric per TAL — competing metric tensions make multi-metric balance impractical. Recommends building separate TALs and comparing.
- **Auto Build produces poorly balanced result:** EZT MCP returns a balance score; if poor, agent surfaces caveat and asks if Monica wants to adjust bias or accept.
- **Auto Build call 2 uses stale TS handle:** EZT MCP rejects with revision mismatch; agent retransmits with full TS or refreshed handle.
- **Map session TAL switcher unavailable in host:** agent falls back to two separate map URLs, one per TAL.
- **Monica wants both TALs kept:** agent skips cleanup and saves TS with both TALs intact.
- **Account dataset very large (10k+):** `ingest_accounts` should define a max batch size; agent may chunk if needed.
- **Part layer mismatch:** some accounts are in Canada but `us_postal` selected; EZT MCP surfaces coverage warnings for out-of-layer coordinates.

### Design conclusions from this scenario

1. **Workload is the primary balance objective and is always present.** Auto Build always includes workload unless `workload_bias=0` is explicitly set. Agents and users should understand this as the default, not an advanced option.
2. **`ingest_accounts` is the right unified primitive.** It handles coordinate passthrough, selective geocoding, and full property passthrough in one call. Splitting into separate tools adds unnecessary complexity.
3. **All account columns pass through as point layer properties.** EZT MCP does not filter or interpret columns. The agent asks Monica which columns to pull; those become the TS schema.
4. **Auto Build takes one optional secondary metric.** It aggregates the `balance_column` by summing across accounts in each part. Workload is computed per-account (travel + dwell) and aggregated similarly.
5. **Multi-metric balancing is explicitly out of scope for v1.** The tension between competing metrics produces poorly balanced results. Build separate TALs for each objective and compare — that's the correct UX.
6. **Metric tension should be surfaced, not hidden.** When both objectives cannot be satisfied simultaneously, the agent should explain the tradeoff clearly, not just present numbers.
7. **Workload estimates carry inherent uncertainty.** Travel time is a statistical approximation (±10–20% vs. routed). This is expected and acceptable at the planning stage. Agents should state this caveat, especially in the final confirmation.
8. **Comparative output: HTML grid is immediate; map is on request.** The grid satisfies the analytical decision need. The map satisfies spatial intuition. Both serve different user modes.
9. **Analysis Presentation Guidance must cover workload framing.** Guidance should include how to explain workload estimates, metric tension, and bias tradeoffs in operator-friendly language.
10. **Dwell time detection is an agent-side responsibility.** The agent should check whether a dwell time column exists in the ingested data; if not (and workload bias > 0), ask Monica for a default before calling Auto Build.

### Auto Build intent translation — reference examples

The following samples show how natural-language Auto Build requests map to the `auto_build_territory_solution` contract. These are normative examples for agent prompt engineering and Functional Spec tool documentation.

| # | Monica says | Mode | `territory_count` | `workload_target_hrs` | `workload_bias` | `metric_bias` | `metric_column` | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | "Create 10 territories" | A | 10 | — | 100 | — | — | Pure workload balance. Agent should confirm dwell time source before building. |
| 2 | "Create 10 territories, each with the same number of accounts" | A | 10 | — | 50 | 50 | `account_count` (synthetic) | Agent surfaces 50-50 default; Monica can override. "Account count" is a synthetic metric = 1 per account, summed to part level. |
| 3 | "Create 10 territories, each with the same number of accounts — do not take workload into account" | A | 10 | — | 0 | 100 | `account_count` | `workload_bias=0`; dwell time not required and must not be requested. Agent may note workload imbalance caveat. |
| 4 | "Create territories each with 40 hours of workload" | B | derived | 40 | 100 | — | — | Mode B, closest-to variant. Agent confirms derived N before building. |
| 5 | "Create territories each with 40 hours of workload, balanced on sales" | B | derived | 40 | 50 | 50 | `sales_volume` | Mode B + secondary metric. Agent surfaces 50-50 default; Monica can override. |

**Key rules encoded by this table:**
- `territory_count` and `workload_target_hrs` are mutually exclusive — exactly one must be supplied.
- When `workload_bias=100` and no metric is named, no bias input is required. This is the pure workload default.
- When a metric is named without a bias, the agent must surface the 50-50 default and invite Monica to adjust.
- When `workload_bias=0`, the agent must not ask for dwell time.
- Mode B requires the agent to confirm the derived territory count before executing the build.
- "Account count" is not a real column — it is a synthetic metric (1 per account) that Auto Build can derive without a column reference. The agent should recognize this intent and map it to the appropriate synthetic metric parameter.

### Open design questions

- ~~Should `ingest_accounts` accept a `dwell_time_column` hint, or should Auto Build resolve it independently?~~ → **Resolved: dwell time is resolved at build time, not ingest time. Resolution order: (1) per-account column specified at build time, (2) agent-held session default scalar, (3) build-time override. EZT MCP always receives a resolved value — column name or scalar — per build call. Session default is agent-owned state, not an EZT MCP concept.**
- Should the `workload` block in `auto_build_territory_solution` be a top-level required field, or optional (defaults to `workload_bias=100` when omitted)? → **Resolved: omitting workload block = pure workload balance (100-0). Block is optional.**
- Travel time algorithm is now documented in CONSTITUTION.md Section 2.10 (quadtree + kd-tree + log-scale speed model, ±10–20% accuracy). Tool documentation should reference this and state the accuracy envelope.
- Max batch size for `ingest_accounts`: TBD. Most customers are in the 10K account range; some have 100K+. Must be designed to handle 100K without chunking if feasible, or define a chunking/streaming contract.
- How does EZT MCP detect invalid coordinates — out-of-layer, out-of-WGS-84-range, or (0, 0)?
- Should the ingestion report include a per-failure `reason` field (no coordinates, geocode failure, address not found, out-of-layer)?
- What null-metric handling strategy for Auto Build — exclude with count reported, treat as zero? Default should be exclude with count reported.
- ~~Should visit frequency column be specified in `ingest_accounts` or at build time?~~ → **Resolved: visit frequency is always an attribute on the account/location data, ingested via `ingest_accounts` as a point layer property. It is never a build-time parameter. Many customers do not have it; it is optional. Customer data is not consistent in format (decimal, inverse-weeks, free text) — the agent is responsible for scrubbing to normalized `visits_per_cycle` float before passing to EZT MCP.**
- Should Analyze compute `workload_hours` as an output metric automatically when point layer properties include dwell time / coordinates, or must the caller explicitly request it?
- Should the styled HTML grid be generated by EZT MCP (as a tool response artifact), rendered by the agent from Analyze facts using presentation guidance, or rendered by the agent host's rendering layer?
- ~~`active_tal_id` after Auto Build: TBD~~ → **Resolved: auto-set to the newly added TAL. Map Component renders the freshest alignment by default. Agent may override explicitly if needed.**
- For the Map Component TAL switcher: driven automatically by the TS `tals[]` array, or does the agent pass a whitelist to `map_session_create`?
- Future: is there a mathematical approach (e.g. Pareto frontier, weighted multi-objective optimization) that could support multiple secondary metrics without the current balance degradation?


---

## Auto Build Scenario Suite

The following scenarios are a focused testbed for the Auto Build tool contract. Each covers a distinct variation of Mode, bias, metric, dwell time, visit frequency, or agent UX. Taken together they should verify that the `auto_build_territory_solution` contract handles every combination we've identified.

All scenarios assume accounts have already been ingested (TS at revision 1 with a point location layer). The agent is the orchestrator; EZT MCP is the compute service.

---

### AB-001 — Pure workload balance, fixed territory count

**Intent:** "Create 10 territories."

**What the agent resolves before calling:**
- No metric named → `workload_bias=100`, no `metric` block needed.
- Workload required → agent checks for dwell time column. None found. Agent asks Monica for a default. Monica says "45 minutes." Agent asks "Use this going forward?" Monica says yes. Session default set to 45 min.

**Tool call:**
```json
{
  "ts": "<ts_handle rev=1>",
  "part_layer": "us_postal",
  "territory_count": 10,
  "tal_label": "Workload Balance",
  "workload": {
    "dwell_time_minutes": 45
  }
}
```

**Expected behavior:**
- EZT MCP appends TAL `tal_workload`, sets `active_tal_id = tal_workload`, returns TS at `revision = 2`.
- Agent confirms: "Built 10 territories balanced on workload (45 min avg dwell). Estimated workload is ±10–20% vs a routed itinerary."

**What this verifies:**
- Default `workload_bias=100` when no metric specified.
- Scalar dwell time accepted.
- Agent session-default UX flow.
- `active_tal_id` auto-set to new TAL.

---

### AB-002 — Pure workload balance, session default already set

**Intent:** "Build another TAL — 12 territories this time."

**What the agent resolves before calling:**
- Session default dwell time already set (45 min from AB-001).
- No metric named → `workload_bias=100`.
- Agent does not re-ask for dwell time.

**Tool call:**
```json
{
  "ts": "<ts_handle rev=2>",
  "part_layer": "us_postal",
  "territory_count": 12,
  "tal_label": "Workload Balance 12T",
  "workload": {
    "dwell_time_minutes": 45
  }
}
```

**Expected behavior:**
- EZT MCP appends second TAL, sets `active_tal_id` to new TAL. TS at `revision = 3`.
- TS now has two TALs: `tal_workload` (10T) and this new one (12T).
- Agent: "Done. 12-territory workload TAL added. You now have two TALs to compare."

**What this verifies:**
- Session default persists across builds without re-prompting.
- Multiple workload-only TALs can accumulate in the same TS.
- `active_tal_id` updates to latest TAL each time.

---

### AB-003 — Workload + metric, 50-50 default bias

**Intent:** "Create 10 territories balanced on sales volume."

**What the agent resolves before calling:**
- Metric named (`sales_volume`) but no bias specified.
- Agent surfaces default: "I'll balance workload and sales volume equally (50-50). Want to adjust?"
- Monica: "That's fine."
- Session default dwell time (45 min) applies.

**Tool call:**
```json
{
  "ts": "<ts_handle>",
  "part_layer": "us_postal",
  "territory_count": 10,
  "tal_label": "Workload + Sales Volume",
  "workload": {
    "dwell_time_minutes": 45
  },
  "metric": {
    "column": "sales_volume",
    "workload_bias": 50,
    "metric_bias": 50
  }
}
```

**Expected behavior:**
- EZT MCP builds TAL balancing workload and `sales_volume` at equal weight.
- Returns TS with new TAL, `active_tal_id` updated.
- Agent notes the metric tension caveat: "These two objectives often conflict — territories with high-revenue accounts may require more travel than low-revenue ones."

**What this verifies:**
- 50-50 default applied when metric named without bias.
- Agent surfaces the default and invites override before building.
- Metric tension caveat is surfaced in agent output.

---

### AB-004 — Workload + metric, explicit non-default bias

**Intent:** "Create 10 territories — mostly balanced on workload, but lean toward equal revenue. Maybe 70-30."

**What the agent resolves before calling:**
- Explicit bias supplied by Monica: `workload_bias=70, metric_bias=30`.
- No need to surface default.

**Tool call:**
```json
{
  "ts": "<ts_handle>",
  "part_layer": "us_postal",
  "territory_count": 10,
  "tal_label": "Workload-Heavy + Revenue",
  "workload": {
    "dwell_time_minutes": 45
  },
  "metric": {
    "column": "sales_volume",
    "workload_bias": 70,
    "metric_bias": 30
  }
}
```

**Expected behavior:**
- Build executes with explicit bias. EZT MCP prioritizes workload balance but allows revenue imbalance to a greater degree.
- Agent confirms: "Built with 70% workload / 30% revenue bias."

**What this verifies:**
- Arbitrary bias splits (not just 50-50 or 100-0) are accepted.
- Agent does not override or normalize an explicitly provided bias.

---

### AB-005 — Pure metric balance (workload irrelevant)

**Intent:** "Create 10 territories, each with the same sales volume. Don't worry about workload."

**What the agent resolves before calling:**
- `workload_bias=0, metric_bias=100`.
- Dwell time NOT required. Agent must not ask for it.

**Tool call:**
```json
{
  "ts": "<ts_handle>",
  "part_layer": "us_postal",
  "territory_count": 10,
  "tal_label": "Equal Revenue",
  "metric": {
    "column": "sales_volume",
    "workload_bias": 0,
    "metric_bias": 100
  }
}
```

**Expected behavior:**
- No `workload` block in the call. EZT MCP builds purely on revenue balance.
- Agent may note: "Territories may vary significantly in rep time burden since workload wasn't factored in."
- Build proceeds without asking for dwell time.

**What this verifies:**
- `workload_bias=0` suppresses dwell time requirement entirely.
- Agent must not ask for dwell time in this path.
- Optional caveat about workload imbalance is appropriate but must not block the build.

---

### AB-006 — Account count balance (synthetic metric, 50-50 default)

**Intent:** "Create 10 territories, each with the same number of accounts."

**What the agent resolves before calling:**
- "Same number of accounts" → synthetic account count metric. No column required.
- Metric named → agent surfaces 50-50 default: "I'll balance workload and account count equally (50-50). Adjust?"
- Monica: "Yes, go ahead."
- Session default dwell time applies.

**Tool call:**
```json
{
  "ts": "<ts_handle>",
  "part_layer": "us_postal",
  "territory_count": 10,
  "tal_label": "Workload + Account Count",
  "workload": {
    "dwell_time_minutes": 45
  },
  "metric": {
    "synthetic": "account_count",
    "workload_bias": 50,
    "metric_bias": 50
  }
}
```

**Expected behavior:**
- EZT MCP computes account count natively (1 per account, summed to part level). No column reference needed.
- Build executes with workload + account count at 50-50.

**What this verifies:**
- Synthetic `account_count` metric supported natively.
- No `column` field required for synthetic metrics.
- Agent correctly maps "same number of accounts" to the synthetic metric parameter without prompting Monica for a column name.

---

### AB-007 — Pure account count balance (workload irrelevant)

**Intent:** "Create 10 territories, each with the same number of accounts — don't take workload into account."

**What the agent resolves before calling:**
- `workload_bias=0, metric_bias=100`, synthetic `account_count`.
- Dwell time not required.
- Agent may note workload imbalance caveat.

**Tool call:**
```json
{
  "ts": "<ts_handle>",
  "part_layer": "us_postal",
  "territory_count": 10,
  "tal_label": "Equal Account Count",
  "metric": {
    "synthetic": "account_count",
    "workload_bias": 0,
    "metric_bias": 100
  }
}
```

**Expected behavior:**
- Pure count balance. No dwell time asked for. Agent notes: "Rep time burden may vary — territories with geographically spread accounts will have higher workload."

**What this verifies:**
- `workload_bias=0` with synthetic metric works.
- Agent note is informative, not blocking.

---

### AB-008 — Mode B: fixed workload target, closest-to variant

**Intent:** "Create territories each with 40 hours of workload."

**What the agent resolves before calling:**
- Mode B. No `territory_count` — it is derived.
- Agent computes estimated total workload from the TS point layer and derives N.
- Agent confirms with Monica: "Based on your accounts, that would give approximately 11 territories. Proceed?"
- Monica: "Yes."
- No metric named → `workload_bias=100`.

**Tool call:**
```json
{
  "ts": "<ts_handle>",
  "part_layer": "us_postal",
  "workload_target_hours": 40,
  "workload_target_variant": "closest_to",
  "tal_label": "40hr Workload Territories",
  "workload": {
    "dwell_time_minutes": 45
  }
}
```

**Expected behavior:**
- EZT MCP derives N = total_workload ÷ 40, builds N territories minimizing deviation from mean.
- Returns TS with new TAL and derived territory count in response metadata.
- Agent reports: "Built 11 territories. Average workload: 39.8 hrs. Std dev: 1.2 hrs. (Estimates are ±10–20% vs a routed itinerary.)"

**What this verifies:**
- Mode B (fixed workload target) contract.
- `territory_count` is absent; derived territory count is returned in response.
- Agent confirms derived N before building.
- Closest-to variant minimizes deviation from mean across all territories.

---

### AB-009 — Mode B: fixed workload target, closest-to-without-exceeding variant

**Intent:** "Create territories each with no more than 40 hours of workload."

**What the agent resolves before calling:**
- Same as AB-008 but `workload_target_variant = "not_to_exceed"`.
- Agent confirms derived N, which may be slightly higher than AB-008 (more territories to avoid any one exceeding 40 hrs).

**Tool call:**
```json
{
  "ts": "<ts_handle>",
  "part_layer": "us_postal",
  "workload_target_hours": 40,
  "workload_target_variant": "not_to_exceed",
  "tal_label": "Max 40hr Workload Territories",
  "workload": {
    "dwell_time_minutes": 45
  }
}
```

**Expected behavior:**
- EZT MCP ensures no territory exceeds 40 hrs, minimizes deviation from mean within that constraint.
- May produce N+1 territories vs AB-008 if the last territory would otherwise exceed the cap.
- Agent: "Built 12 territories. No territory exceeds 40 hrs. Average workload: 36.7 hrs."

**What this verifies:**
- `not_to_exceed` variant enforces the cap as a hard constraint.
- Territory count output may differ from `closest_to` for the same target.
- Both variants minimize deviation from mean — one outlier territory is not acceptable in either.

---

### AB-010 — Mode B: fixed workload target + secondary metric

**Intent:** "Create territories with about 40 hours each, balanced on sales too."

**What the agent resolves before calling:**
- Mode B + secondary metric. Agent surfaces 50-50 default.
- Agent confirms derived N before building.

**Tool call:**
```json
{
  "ts": "<ts_handle>",
  "part_layer": "us_postal",
  "workload_target_hours": 40,
  "workload_target_variant": "closest_to",
  "tal_label": "40hr + Sales Balance",
  "workload": {
    "dwell_time_minutes": 45
  },
  "metric": {
    "column": "sales_volume",
    "workload_bias": 50,
    "metric_bias": 50
  }
}
```

**Expected behavior:**
- EZT MCP derives N from workload totals, then balances on workload + sales at 50-50 across those N territories.
- Agent notes metric tension caveat.

**What this verifies:**
- Mode B + secondary metric can be combined.
- Territory count is still derived from workload target, not from metric.

---

### AB-011 — Visit frequency column present, workload scaled

**Intent:** "Create 10 territories." Account data includes `visit_freq_per_week` column (already ingested).

**What the agent resolves before calling:**
- Visit frequency column present in TS point layer. Agent tells Monica: "I see a `visit_freq_per_week` column — I'll use that to scale workload per account. Values range from 0.25 to 4. Does that look right?"
- Monica confirms.
- Agent passes `visit_frequency_column` to the build.

**Tool call:**
```json
{
  "ts": "<ts_handle>",
  "part_layer": "us_postal",
  "territory_count": 10,
  "tal_label": "Freq-Weighted Workload",
  "workload": {
    "dwell_time_minutes": 45,
    "visit_frequency_column": "visit_freq_per_week"
  }
}
```

**Expected behavior:**
- EZT MCP multiplies both dwell time and estimated travel time by `visit_freq_per_week` for each account.
- Accounts with higher visit frequency contribute proportionally more to territory workload.
- Agent notes estimated workload includes frequency scaling.

**What this verifies:**
- `visit_frequency_column` accepted in the workload block.
- Null/absent values default to frequency = 1 without error.
- Agent surfaces the column and value range for Monica to confirm before building.

---

### AB-012 — Visit frequency as raw text, agent normalization required

**Intent:** "Create 10 territories." Account data includes `visit_schedule` column with values like `"twice per week"`, `"monthly"`, `"every 3 weeks"`.

**What the agent resolves before calling:**
- Raw text frequency column detected. Agent cannot pass it directly to EZT MCP.
- Agent samples values: "Your `visit_schedule` column has text values like 'twice per week', 'monthly', 'every 3 weeks'. I'll normalize these to visits-per-week — does this look right? twice/week → 2.0, monthly → 0.23, every 3 weeks → 0.33."
- Monica confirms.
- Agent writes normalized `visits_per_week` as a new point layer property on the TS before building.

**Tool call (after normalization):**
```json
{
  "ts": "<ts_handle with normalized visits_per_week property>",
  "part_layer": "us_postal",
  "territory_count": 10,
  "tal_label": "Freq-Weighted Workload",
  "workload": {
    "dwell_time_minutes": 45,
    "visit_frequency_column": "visits_per_week"
  }
}
```

**Expected behavior:**
- EZT MCP receives a clean numeric column. No text parsing required on its end.
- Agent is responsible for the normalization step and must surface the mapping to Monica for confirmation.

**What this verifies:**
- EZT MCP only accepts numeric `visits_per_cycle` float — it never parses text or inverse formats.
- Agent owns scrubbing. EZT MCP contract is clean.
- Ambiguous values (e.g. `"2"` — twice per cycle or every 2 cycles?) require Monica confirmation.

---

### AB-013 — Build-time dwell time override (ignores session default)

**Intent:** "For this build, use 1 hour per visit instead of our usual 30 minutes."

**What the agent resolves before calling:**
- Session default is 30 min. Monica explicitly overrides for this build.
- Agent applies override for this call only. Session default remains 30 min.

**Tool call:**
```json
{
  "ts": "<ts_handle>",
  "part_layer": "us_postal",
  "territory_count": 10,
  "tal_label": "1hr Dwell Workload",
  "workload": {
    "dwell_time_minutes": 60
  }
}
```

**Expected behavior:**
- Build uses 60-min dwell. Session default not changed.
- Agent confirms: "Built with 1-hour dwell time. Your session default of 30 minutes is unchanged."

**What this verifies:**
- Build-time override is per-call only.
- Session default persists unless Monica explicitly updates it.
- Agent should confirm which dwell time was used and that the default is unchanged.

---

### AB-014 — Per-account dwell time column (overrides scalar default)

**Intent:** "Create 10 territories." Account data includes `avg_visit_hrs` column (e.g. 0.5 for quick stops, 2.0 for complex accounts).

**What the agent resolves before calling:**
- Agent scans columns, finds `avg_visit_hrs`. Asks Monica: "I see an `avg_visit_hrs` column — should I use that as per-account dwell time instead of the session default?"
- Monica: "Yes."
- Per-account column takes precedence over session default.

**Tool call:**
```json
{
  "ts": "<ts_handle>",
  "part_layer": "us_postal",
  "territory_count": 10,
  "tal_label": "Per-Account Dwell Workload",
  "workload": {
    "dwell_time_column": "avg_visit_hrs"
  }
}
```

**Expected behavior:**
- EZT MCP uses `avg_visit_hrs` per account. No scalar default applied.
- Agent: "Using per-account dwell times from `avg_visit_hrs` (range: 0.5–2.0 hrs)."

**What this verifies:**
- Per-account column takes precedence over scalar default when specified.
- `dwell_time_column` and `dwell_time_minutes` are mutually exclusive in the workload block.
- Agent surfaces the column and value range before building.

---

### AB-015 — Multi-metric request (not supported — agent explains)

**Intent:** "Create 10 territories balanced on both store count and sales volume."

**What the agent resolves before calling:**
- Multiple secondary metrics requested → not supported in v1.
- Agent explains: "EZT MCP supports one secondary metric per TAL. Balancing on multiple metrics simultaneously creates competing tensions that typically produce a poorly balanced result on all dimensions. The recommended approach is to build separate TALs — one balanced on store count, one on sales volume — and compare them."
- Agent offers to proceed with two separate TAL builds.
- Monica: "OK, do both."
- Agent runs AB-003 and AB-006 style calls in sequence on the same TS.

**Expected behavior:**
- No tool call with multiple metrics is made.
- Agent explains the constraint clearly and offers the correct alternative.
- Two separate TAL builds produce a TS with two TALs, ready for comparative analysis.

**What this verifies:**
- Agent must intercept multi-metric requests before calling Auto Build.
- The agent — not EZT MCP — owns the "not supported" explanation and remediation path.
- EZT MCP never receives a multi-metric build call.

---

### AB-016 — Mode A and Mode B mutually exclusive

**Intent:** "Create exactly 10 territories, each with about 40 hours of workload."

**What the agent resolves before calling:**
- Both `territory_count` and `workload_target_hours` specified → mutually exclusive.
- Agent explains: "I can either build a fixed number of territories (10) balanced on workload, or build territories sized to ~40 hours each and let the count be derived — but not both at once. Which would you prefer?"
- Monica chooses one.

**Expected behavior:**
- No tool call is made until Monica resolves the ambiguity.
- Agent explains the two modes clearly and lets Monica decide.

**What this verifies:**
- Agent must detect and resolve the Mode A/B conflict before calling Auto Build.
- EZT MCP never receives a call with both `territory_count` and `workload_target_hours` set.

## Scenario Backlog

Add future scenarios below this line. Candidate categories:

- Direct Build from uploaded ZIP-to-territory spreadsheet
- Account Build from account owner/manager grouping
- Executive read-only sharing workflow
- Power BI export/projection workflow
- Repair-heavy imported alignment workflow
- Meeting review with Teams/shared-stage Map Component
- Stale/expired map session recovery
