# SCENARIOS.md — EZT MCP Workflow Scenarios

**Version:** 0.2.0
**Date:** 2026-05-11
**Status:** Scenario collection — draft

This document collects concrete human/agent/EZT MCP scenarios before the Functional Spec is finalized. The goal is to stress-test the product architecture against realistic workflows, especially where natural language, map interaction, TS state, MCP tools, resources, and notifications intersect.

Scenarios should be written from the user's perspective first, then mapped to the proposed architecture. As this file grows, it should help validate tool boundaries, resource contracts, notification behavior, TS revision handling, Map Component responsibilities, and agent orchestration patterns.

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

## Scenario Backlog

Add future scenarios below this line. Candidate categories:

- Manager-directed conversational build from CRM data
- Direct Build from uploaded ZIP-to-territory spreadsheet
- Account Build from account owner/manager grouping
- Auto Build revenue-balanced TAL, then compare with headcount-balanced TAL
- Executive read-only sharing workflow
- Power BI export/projection workflow
- Repair-heavy imported alignment workflow
- Multi-TAL comparison and choosing one to persist
- Meeting review with Teams/shared-stage Map Component
- Stale/expired map session recovery
