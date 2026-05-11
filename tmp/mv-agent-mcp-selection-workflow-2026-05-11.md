# EZT MCP — Map Visual / Agent / MCP Selection Workflow Notes

Date: 2026-05-11
Context: Monica asks her agent to open yesterday's Territory Solution (TS) with an active Territory Alignment Layer (TAL), selects ZIPs along a territory boundary in the Map Visual, asks for analysis, then realigns the selected ZIPs from T1 to T2.

## Working thesis

The Map Visual should be a live spatial I/O surface attached to an MCP session, not an MCP client itself.

- The agent remains Monica's conversational orchestrator and durable TS custodian.
- EZT MCP remains durably stateless, but may create short-lived live map sessions as transport/session coordination objects.
- The Map Visual talks to EZT MCP over normal web protocols using a short-lived map session token.
- The agent talks to EZT MCP over MCP.
- The bridge between those worlds is MCP Resource Subscriptions: map-session resources change, EZT MCP emits MCP notifications, and the agent reacts.

This preserves the earlier rule: the Map Visual does not independently decide territory operations. It emits selections and renders refreshed TS revisions. The agent decides what tool calls to make.

## Recommended MCP / web surface

### MCP tools

#### `map_session_create`
Creates a short-lived interactive map session for a TS.

Input:
- `ts` or `ts_handle`
- `active_tal_id`
- `mode`: `view | select`
- optional `part_layer`
- optional `expires_in_seconds`
- optional `selection_policy` / `allowed_actions`

Output:
- `map_session_id`
- `map_url` — link/iframe URL for the Map Visual
- `selection_resource_uri` — e.g. `ezt://map-sessions/{map_session_id}/selection`
- `state_resource_uri` — e.g. `ezt://map-sessions/{map_session_id}/state`
- `ts_handle` / `ts_identity`
- `expires_at`

#### `analyze_territory_solution`
Existing Analyze tool, extended with optional analysis scope.

Optional input additions:
- `tal_ids`
- `scope`: `{ "type": "part_ids", "part_layer": "us_zips", "part_ids": [...] }`
- optional `compare_against`: territory IDs or `active_tal_id`

Output should include selection-level aggregates such as:
- selected part count
- selected account count
- selected metric totals (`annual_revenue`, etc.)
- current territory assignment summary
- impact if moved from source territory to target territory when requested
- caveats for split parts, missing points, unmatched part IDs, or stale TS revision

#### `realign_territory_solution`
Existing Realign tool.

Input:
- `ts` or `ts_handle`
- `tal_id`
- move operation: `part_ids[]`, `from_territory_id`, `to_territory_id`
- optional `expected_revision` / `expected_content_hash`
- optional `map_session_id` to refresh the live Map Visual after success

Output:
- updated TS or `ts_handle`
- updated `ts_identity`
- changed territories summary
- optional `map_refresh_resource_uri` / notification metadata

### MCP resources

#### `ezt://map-sessions/{id}/selection`
Latest committed selection from the Map Visual.

Example payload:
```json
{
  "map_session_id": "ms_01J...",
  "event_id": "evt_01J...",
  "event_type": "selection.committed",
  "created_at": "2026-05-11T15:05:00Z",
  "ts_id": "ts_01HX...",
  "ts_revision": 7,
  "active_tal_id": "tal_revenue",
  "part_layer": "us_zips",
  "part_id_property": "zip",
  "part_ids": ["32309", "32308", "32312"],
  "selection_method": "lasso",
  "selected_count": 3,
  "current_assignments": [
    { "territory_id": "T1", "part_ids": ["32309", "32308", "32312"] }
  ]
}
```

When this resource changes, EZT MCP emits a resource notification to subscribed MCP clients. OpenClaw can receive this through MCP Resource Subscriptions and place it into the agent's live event queue.

#### `ezt://map-sessions/{id}/state`
Current short-lived live map state.

Useful fields:
- current mode (`view | select`)
- active TAL
- active TS identity / revision / hash
- selection status
- last refresh event
- expires_at

## Web channel between Map Visual and EZT MCP

The Map Visual URL should contain only a short-lived, non-guessable map session token or exchange code, never a customer API key and never raw TS data in the query string.

The Map Visual should use one of these patterns:

1. **HTTP POST + SSE/WebSocket**
   - MV fetches initial state from `/map-sessions/{id}` using bearer session token.
   - MV POSTs `selection.committed` events to `/map-sessions/{id}/selection`.
   - MV listens via SSE/WebSocket for `ts.updated`, `mode.changed`, or `session.expired`.

2. **Iframe `postMessage` for agent-host canvas plus server relay**
   - Useful in OpenClaw Canvas if the host wants direct local UI messages.
   - Still route authoritative selection commits through EZT MCP so resource subscriptions notify the agent consistently.

Recommendation: use HTTP POST + SSE/WebSocket as the canonical protocol, with `postMessage` only as an embedding convenience.

## End-to-end scenario

1. Monica: “Open yesterday’s TS that has a TAL.”
2. Agent retrieves the TS from Monica/customer storage. The TS has `active_tal_id` or the agent chooses one.
3. Agent calls `map_session_create(ts|ts_handle, active_tal_id, mode="select")`.
4. EZT MCP returns `map_url`, `map_session_id`, and resource URIs.
5. Agent subscribes to `ezt://map-sessions/{id}/selection` and opens/embeds `map_url`.
6. Monica selects ZIP codes along a T boundary and clicks Done.
7. MV POSTs `selection.committed` to EZT MCP with `part_ids[]`, active TAL, TS revision/hash, and selection metadata.
8. EZT MCP updates the short-lived map-session selection resource and emits an MCP resource notification.
9. OpenClaw receives the notification: “Monica selected ZIPs: 32309, 32308, ...”.
10. Agent calls `ep_search` or reads an MCP prompt/resource for territory-alignment guidance, then injects that guidance into its local reasoning context.
11. Agent calls `analyze_territory_solution` with the TS and `scope=part_ids`.
12. Agent presents a compact analysis grid: ZIPs selected, accounts, sales volume, current territory, likely move impact.
13. Monica: “Move those from T1 to T2.”
14. Agent calls `realign_territory_solution(ts|ts_handle, tal_id, part_ids, from=T1, to=T2, map_session_id)`.
15. EZT MCP updates the TAL, returns updated TS/revision/hash, and emits a map session `ts.updated` event.
16. MV receives the refresh event, fetches/renders the updated TS, and shows the new alignment.
17. Agent persists the updated TS back to Monica/customer storage.

## Key design choices

### 1. Selection events should be explicit commits
The MV should not notify the agent on every click/lasso drag. It should maintain local transient selection state and emit only after Monica clicks Done. This avoids noisy agent interruptions and aligns with Monica's intent.

### 2. Resource notifications carry enough data for awareness, not full analysis
The selection notification can include `part_ids[]`, selected count, and current assignments. It should not attempt to include all account/revenue analysis. The agent should call Analyze for authoritative metrics.

### 3. Analyze needs selection scope
The current Analyze concept is TS/TAL-level. This scenario needs selection-level analysis. Best fit: extend Analyze with optional `scope`, instead of adding a separate `analyze_selection` tool. That keeps metrics semantics in one tool.

### 4. Live map sessions are transient coordination, not durable storage
A map session may cache TS state long enough for interactive UX, but the agent remains the durable TS owner. The session expires. Cache miss or expired session means the agent recreates the session from its saved TS.

### 5. Realign should support optimistic concurrency
Realign should accept `expected_revision` or `expected_content_hash`. If Monica selects against TS revision 7 but the agent tries to realign revision 8, the tool should return a structured stale-selection error and ask the agent to refresh/reconfirm.

### 6. MV refresh should be event-driven
After Realign succeeds, EZT MCP should notify the MV through the map session channel (`ts.updated`). The agent also receives the updated TS identity and persists it. The MV is a visual consumer of the same new revision.

## Open decisions

1. Whether `map_session_create` belongs in the MVP tool set or is part of a separate “share/map” surface.
2. Exact resource URI taxonomy.
3. Whether the agent subscribes to selection only, or also to state/refresh resources.
4. Whether OpenClaw Canvas embed should use direct postMessage in addition to MCP notifications.
5. How much selection context the MV should compute locally from part-layer PMTiles vs ask the server to enrich from PostGIS/TS.
6. How to package analysis-presentation guidance: MCP prompt/resource vs `ANALYSIS_DESIGN.md` plus resource wrapper.
