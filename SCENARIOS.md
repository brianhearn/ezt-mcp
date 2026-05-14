# SCENARIOS.md — EZT MCP Workflow Scenarios

**Version:** 0.9.4
**Date:** 2026-05-14
**Status:** Lean scenario registry — draft

This document is a compact registry of human/agent/EZT MCP workflows. It exists to validate that the product architecture still covers real scenarios as tool contracts and implementation details evolve.

Keep scenarios terse: narrative steps only. Put contracts, JSON, schemas, and implementation detail in `CONSTITUTION.md` or the future `FUNCTIONAL_SPEC.md`.

## Key Terms

Abbreviations used throughout this document. Full definitions in [CONSTITUTION.md §4.1](CONSTITUTION.md).

| Abbreviation | Full Term | Short Definition |
|---|---|---|
| **TS** | Territory Solution | A GeoJSON FeatureCollection — the universal EZT MCP geometry artifact. Contains 0-N point location layers and 0-N TALs, plus solution-level metadata. |
| **TAL** | Territory Alignment Layer | One named territory arrangement inside a TS, e.g. "By Revenue Q1". A TS can hold multiple TALs for side-by-side comparison. |
| **MC** | Map Component | The browser-based map surface embedded in the agent host. Renders TS geometry over PMTiles basemap/part layers. Supports `view` and `select` modes. |
| **MV** | Map Visual / Map Component | Used interchangeably with MC in older notes; refers to the same Map Component surface. |
| **MCP** | Model Context Protocol | The open protocol used for tool, resource, and prompt communication between the agent and EZT MCP Server. |
| **EP** | ExpertPack | Structured domain knowledge pack backing EZT MCP's `ep_search` knowledge retrieval surface. |
| **T** | Territory | A single named geographic area within a TAL — the dissolved union of one or more parts, e.g. ZIP codes. |
| **P / Part** | Part | The atomic geographic unit, e.g. one ZIP code polygon, from which territories are composed. |

---

## Core Workflow Scenarios

### S001 — Monica selects ZIPs along a territory boundary and realigns them

1. Monica tells her agent: "Open yesterday's territory solution and let me adjust the boundary on the map."
2. The agent retrieves the TS from Monica/customer storage and opens a select-mode MC session on the active TAL.
3. Monica selects several ZIPs along the boundary and clicks Done.
4. EZT MCP notifies the agent that the selection was committed.
5. The agent calls Analyze for the selected ZIPs and shows Monica the current assignment and likely metric impact.
6. Monica says: "Move those from T1 to T2."
7. The agent calls Realign on the active TAL with optimistic concurrency.
8. EZT MCP updates the TS, repairs geometry if needed, and refreshes the live MC session.
9. The agent persists the updated TS and summarizes the impact.

Decision: `get_map_visualization` is v1; exact resource payload schemas move to `FUNCTIONAL_SPEC.md` and `schemas/`.

### S002 — Monica emails a read-only latest East Coast TS view to her boss

1. Monica tells her agent: "Send my boss the latest East Coast territory view."
2. The agent retrieves the latest East Coast TS from Monica/customer storage.
3. The agent calls `get_map_visualization` in read-only `view` mode for the active TAL.
4. EZT MCP returns a secure temporary browser URL.
5. The agent analyzes the TS and drafts a short executive summary.
6. The agent sends the boss the read-only link and summary through Monica's approved email workflow.
7. Monica's boss opens the URL in a browser and reviews the latest map without editing it.

Decision: V1 sharing is browser URL / OpenClaw Canvas plus Analyze-backed narrative; Teams, Power BI embedding, and formal export contracts are post-MVP.

### S003 — Monica pulls CRM accounts and auto-builds two TALs for side-by-side comparison

1. Monica tells her agent: "Pull my CRM accounts and build one alignment by revenue and another by account count."
2. The agent retrieves CRM account data and converts it into standard ingest input.
3. EZT MCP geocodes rows that need coordinates and returns a TS with a point layer.
4. The agent asks any required dwell-time or visit-frequency clarification.
5. The agent calls Auto Build once for the revenue-oriented TAL.
6. EZT MCP appends the new TAL and sets it as active.
7. The agent calls Auto Build again for the account-count-oriented TAL.
8. EZT MCP appends the second TAL and sets it as active.
9. The agent calls Analyze across both TALs.
10. Monica sees a side-by-side comparison and can switch between TALs in the MC.

Decision: polished comparison presentation belongs in Analysis Presentation Guidance, not scenario prose.

### S004 — Developer visually verifies a generated TAL during implementation

1. Brian or an implementation agent runs a build/realign/analyze fixture that produces or references a TS.
2. The agent calls `get_map_visualization` in `view` mode for the active TAL.
3. EZT MCP returns a browser/OpenClaw Canvas URL.
4. Brian visually checks territory geometry, rollups, labels, point overlays, active TAL, and obvious repair side effects.
5. The development loop treats visual verification as a required gate for geometry-producing changes.

Decision: minimal read-only MC visualization should be implemented before deeper build/realign/auto-build work, because JSON-only tests cannot reveal many spatial defects.

---

## Geocode Address Scenarios

### GC-001 — Monica bulk-geocodes a customer address list before ingest

1. Monica tells her agent: "Geocode this customer address list so I can build territories from it."
2. The agent reads the uploaded list and identifies address columns.
3. EZT MCP geocodes the addresses and returns standardized coordinates.
4. The agent shows Monica a short success summary and any low-confidence matches.
5. The agent uses the geocoded output as input for account ingestion.

### GC-002 — Geocoder partial failure returns a structured failure list

1. Monica gives the agent an address list with several bad or incomplete addresses.
2. The agent sends the valid address rows to EZT MCP for geocoding.
3. EZT MCP geocodes the rows it can and returns structured failures for the rest.
4. The agent reports exactly which rows failed and why.
5. Monica corrects the failed addresses or chooses to proceed without them.

### GC-003 — Agent skips geocoding when coordinates already exist

1. Monica uploads account data that already contains latitude and longitude columns.
2. The agent detects that valid coordinates are already present.
3. The agent skips unnecessary geocoding and tells Monica why.
4. EZT MCP ingests the rows directly as a point layer.
5. Monica avoids extra cost, latency, and geocoder drift.

---

## Ingest Accounts Scenarios

### IA-001 — Monica ingests account CSV and preserves all columns

1. Monica tells her agent: "Use this account CSV for territory planning."
2. The agent identifies coordinates or address fields and prepares the rows.
3. EZT MCP ingests the accounts as a TS point layer.
4. All non-geometry columns pass through as point properties.
5. Monica can later balance, analyze, filter, and label using those original columns.

### IA-002 — Mixed coordinates and addresses in one account file

1. Monica uploads account data where some rows have coordinates and others only have addresses.
2. The agent detects the mixed location state.
3. EZT MCP keeps valid coordinate rows as-is and geocodes only rows that need it.
4. The agent reports geocoding successes and failures separately.
5. Monica receives one clean TS point layer.

### IA-003 — Agent detects a dwell-time column candidate

1. Monica uploads account data with a column like `service_minutes` or `dwell_time`.
2. The agent detects that the column may represent per-account dwell time.
3. The agent asks Monica to confirm whether it should be used for workload.
4. Monica confirms or rejects the candidate.
5. The agent records the decision and proceeds with ingestion/build planning.

### IA-004 — Agent detects visit-frequency column and surfaces range

1. Monica uploads account data with a likely visit-frequency column.
2. The agent detects the column and inspects its value range.
3. The agent normalizes obvious raw formats when safe.
4. The agent asks Monica to confirm ambiguous frequency semantics.
5. EZT MCP receives normalized visit frequency as point-layer properties.

### IA-005 — Ingestion failures are returned, not silently dropped

1. Monica uploads a messy account file.
2. The agent prepares the rows and sends them to EZT MCP for ingestion.
3. EZT MCP ingests valid rows and returns structured failures for invalid rows.
4. The agent tells Monica how many rows succeeded and lists actionable failures.
5. Monica decides whether to fix the file or continue with partial data.

---

## Direct Build Scenarios

### DB-001 — Monica builds a TAL from an existing ZIP-to-territory file

1. Monica tells her agent: "Build a territory layer from this ZIP-to-territory Excel file."
2. The agent reads the Excel or CSV and maps ZIPs to territory labels.
3. EZT MCP creates a TAL from the direct assignments.
4. EZT MCP dissolves ZIP parts into territories and repairs simple geometry issues.
5. The agent returns a TS containing the new TAL.

### DB-002 — Direct Build input has gaps and Repair fills holes

1. Monica uploads a ZIP-to-territory file with some unassigned ZIPs.
2. The agent asks EZT MCP to Direct Build from the provided assignments.
3. EZT MCP identifies assignment gaps.
4. Repair fills holes according to the product rules.
5. The agent reports both Monica's original assignments and any repair side effects.

### DB-003 — Direct Build appends a TAL to an existing TS

1. Monica tells her agent: "Add this legacy alignment to the territory solution we already opened."
2. The agent retrieves the existing TS.
3. EZT MCP Direct Builds a new TAL from Monica's assignment file.
4. EZT MCP appends the TAL to the TS instead of replacing existing TALs.
5. Monica can compare the legacy TAL against newer TALs.

### DB-004 — Direct Build with a three-level territory hierarchy

1. Monica uploads a spreadsheet with columns: Region, District, Territory, ZIP.
2. The agent maps each row to `territory_path: [Region, District, Territory]` and `part_id: ZIP`.
3. EZT MCP builds a hierarchical TAL: rollup nodes for Regions and Districts, leaf territories holding ZIPs.
4. EZT MCP returns `hierarchy_summary` showing max depth 2, leaf count, and rollup count.
5. Monica's agent confirms the structure and presents the map.

### DB-005 — Direct Build from legacy pipe-delimited territory names

1. Monica supplies a CSV with a `TerritoryName` column using pipe-delimited values: `East|Southeast|FL-01`.
2. The agent splits each value on `|` to produce a `territory_path` array before calling `direct_build`.
3. EZT MCP builds the TAL with the correct hierarchy — no pipes reach the tool.
4. Monica's regions and sub-regions render correctly without any special naming conventions.

---

## Account Build Scenarios

### ACB-001 — Account Build groups by territory name

1. Monica's CRM data includes a `territory_name` column.
2. Monica tells her agent: "Build territories from the territory names in CRM."
3. The agent ingests the accounts as a point layer.
4. EZT MCP groups accounts by `territory_name` and creates a TAL.
5. Monica sees territories that reflect the CRM grouping.

### ACB-002 — Account Build groups by rep name and repairs non-contiguous regions

1. Monica's CRM data assigns accounts to reps.
2. Some reps cover scattered, non-contiguous regions.
3. The agent asks EZT MCP to Account Build using rep name as the grouping attribute.
4. EZT MCP creates the grouped TAL and runs Repair to restore valid territory geography.
5. The agent reports any repair decisions that changed the raw grouping outcome.

### ACB-003 — Numeric territory code is treated as a label, not a metric

1. Monica's account data includes a numeric territory code column.
2. Monica tells her agent to build territories using that code.
3. The agent treats the numeric code as a grouping label.
4. EZT MCP creates territories by matching codes, not by balancing the numeric values.
5. Monica sees a direct grouped alignment with codes preserved as labels.

---

## Auto Build Scenario Suite

### AB-001 — Pure workload balance, fixed territory count

1. Monica tells her agent: "Create ten balanced sales territories from these accounts."
2. The agent interprets this as Mode A with a fixed territory count.
3. EZT MCP builds territories using workload as the sole balance objective.
4. Monica sees a new TAL with ten workload-balanced territories.

### AB-002 — Pure workload balance with session default dwell time

1. Monica has already told the agent her default visit dwell time.
2. Monica asks for another workload-balanced build.
3. The agent uses the existing session default without asking again.
4. EZT MCP builds the TAL using that dwell-time assumption.
5. The agent reminds Monica which default was used.

### AB-003 — Workload plus metric with default 50-50 bias

1. Monica tells her agent: "Balance these by workload and revenue."
2. The agent sees a named metric but no explicit weighting.
3. The agent uses the default 50-50 workload/metric bias.
4. EZT MCP builds the TAL with both objectives.
5. Monica sees the tradeoff summarized clearly.

### AB-004 — Workload plus metric with explicit non-default bias

1. Monica says: "Prioritize revenue, but keep workload reasonable."
2. The agent translates that into a non-default workload/metric bias.
3. EZT MCP builds a TAL using the explicit weighting.
4. The agent explains the weighting in plain language.
5. Monica reviews a revenue-prioritized alignment.

### AB-005 — Pure metric balance

1. Monica says: "Ignore workload and balance purely by revenue."
2. The agent sets workload influence to zero.
3. EZT MCP builds territories using the selected metric only.
4. The agent warns Monica that drive/workload balance may be poor.
5. Monica reviews the metric-balanced TAL.

### AB-006 — Account count balance with default 50-50 bias

1. Monica says: "Balance by workload and account count."
2. The agent treats account count as a supported synthetic metric.
3. The agent applies the default 50-50 workload/account-count bias.
4. EZT MCP builds the TAL.
5. Monica sees both workload and account-count balance results.

### AB-007 — Pure account count balance

1. Monica says: "Just make the territories have equal numbers of accounts."
2. The agent treats this as pure account-count balancing.
3. EZT MCP builds a TAL using synthetic account count only.
4. The agent notes that workload and revenue were not optimized.
5. Monica reviews an equal-account-count alignment.

### AB-008 — Mode B fixed workload target, closest-to variant

1. Monica says: "Create as many territories as needed, each close to 40 hours of work."
2. The agent interprets this as Mode B with a fixed workload target.
3. EZT MCP builds territories closest to the target workload.
4. The agent reports the resulting territory count and variance from target.
5. Monica reviews whether the generated count is acceptable.

### AB-009 — Mode B fixed workload target, not-to-exceed variant

1. Monica says: "No territory should exceed 40 hours of work."
2. The agent interprets this as Mode B with a not-to-exceed target.
3. EZT MCP builds enough territories to stay under the workload cap where feasible.
4. The agent reports any territories that could not satisfy the cap.
5. Monica reviews the capacity-driven alignment.

### AB-010 — Mode B fixed workload target plus secondary metric

1. Monica says: "Target 40 hours per territory and keep revenue balanced too."
2. The agent interprets fixed workload as the primary Mode B objective.
3. The agent includes revenue as the secondary metric.
4. EZT MCP builds the TAL using workload target plus metric pressure.
5. Monica sees target adherence and revenue balance side by side.

### AB-011 — Visit frequency column scales workload

1. Monica's account data includes normalized visit frequency.
2. Monica asks for workload-balanced territories.
3. The agent passes visit frequency through as account data.
4. EZT MCP scales dwell and travel workload by visit frequency.
5. Monica sees workload that reflects repeated visits, not just account count.

### AB-012 — Raw visit frequency text is normalized by the agent

1. Monica's file has visit frequency values like "weekly", "monthly", or "2x/month".
2. The agent recognizes the column but does not pass raw text directly.
3. The agent normalizes values into visits-per-cycle numbers or asks Monica about ambiguous values.
4. EZT MCP receives clean numeric visit frequency.
5. Monica sees a build based on normalized frequency assumptions.

### AB-013 — Build-time dwell override beats session default

1. Monica has a session default dwell time.
2. Monica says: "For this build, assume 30 minutes per visit."
3. The agent treats 30 minutes as a build-time override.
4. EZT MCP uses the override for this build only.
5. The agent leaves the session default unchanged unless Monica says otherwise.

### AB-014 — Per-account dwell time column overrides scalar default

1. Monica's account data contains a confirmed dwell-time column.
2. Monica asks for a workload build.
3. The agent passes the per-account dwell values through.
4. EZT MCP uses row-level dwell values instead of the scalar default.
5. Monica sees workload reflecting different service times by account.

### AB-015 — Multi-metric request is not supported

1. Monica says: "Balance workload, revenue, account count, and potential all at once."
2. The agent recognizes that multi-metric balancing is outside the current contract.
3. The agent explains the limitation and asks Monica to choose one secondary metric.
4. Monica chooses the metric that matters most.
5. EZT MCP builds using workload plus the selected single metric.

### AB-016 — Mode A and Mode B are mutually exclusive

1. Monica says: "Make exactly ten territories, each capped at 40 hours."
2. The agent recognizes a conflict between fixed count and fixed workload target.
3. The agent asks Monica which constraint should control the build.
4. Monica chooses fixed count or workload target.
5. EZT MCP builds using the selected mode only.

---

## Realign Scenarios

### RL-001 — Monica moves specific ZIPs by text only

1. Monica tells her agent: "Move ZIPs 32308 and 32309 from T3 to T4."
2. The agent identifies the active TS and TAL.
3. EZT MCP Realigns those ZIPs from T3 to T4.
4. EZT MCP repairs affected territory geometry if needed.
5. The agent saves the updated TS and summarizes the change.

### RL-002 — Monica splits an oversized territory into two

1. Monica says: "T7 is too large; split it into two balanced territories."
2. The agent analyzes T7 to understand size and workload.
3. EZT MCP creates a proposed split within the same TAL.
4. Monica reviews the proposed new territories.
5. The agent commits the split after Monica approves.

Decision: territory split is v1 via Auto Build Scoped Split, not Realign.

### RL-003 — Departed rep's territory is absorbed by adjacent territories

1. Monica says: "Jordan left; absorb their territory into neighboring territories."
2. The agent identifies Jordan's territory and adjacent candidates.
3. EZT MCP redistributes the parts into neighboring territories instead of leaving an empty territory.
4. Repair preserves contiguity and fills topology gaps.
5. The agent reports where Jordan's parts went.

### RL-004 — Realign targets a specific TAL when TS has multiple TALs

1. Monica has a TS containing multiple TALs.
2. Monica says: "Make this move only in the revenue alignment."
3. The agent targets the named TAL explicitly.
4. EZT MCP modifies only that TAL.
5. Monica sees the other TALs remain unchanged.

### RL-005 — Stale revision rejection triggers refresh and retry

1. Monica asks the agent to realign parts from a TS that changed since the map selection.
2. The agent calls Realign with the old revision.
3. EZT MCP rejects the request as stale.
4. The agent reloads the current TS and refreshes the MC.
5. Monica reconfirms the move before the agent retries.

---

## Analyze Scenarios

### AN-001 — Monica analyzes a TS loaded from storage

1. Monica tells her agent: "Analyze the territory solution I saved last week."
2. The agent retrieves the TS from storage.
3. The agent calls Analyze without needing a recent build.
4. EZT MCP analyzes the current TS content.
5. Monica receives a current analysis of the loaded solution.

### AN-002 — Single TAL analysis

1. Monica asks: "How balanced is this alignment?"
2. The agent targets the active TAL.
3. EZT MCP computes balance scores, outliers, exceptions, and caveats.
4. The agent formats the findings for an operator.
5. Monica sees what needs attention first.

### AN-003 — Cross-TAL comparison

1. Monica asks: "Which of my two alignments is better balanced?"
2. The agent identifies the two TALs to compare.
3. EZT MCP analyzes both TALs in one comparison.
4. The agent explains the tradeoffs and recommends a winner if the data supports it.
5. Monica can switch between both TALs in the MC.

### AN-004 — Polygon-area-only analysis with no point layers

1. Monica opens a TS that has territories but no account point layers.
2. Monica asks for analysis anyway.
3. EZT MCP analyzes available geography-only signals such as territory area and part counts.
4. The agent clearly notes which business metrics are unavailable.
5. Monica still gets useful geography-level diagnostics.

### AN-005 — Agent uses Analysis Presentation Guidance

1. Monica asks for an executive-ready analysis summary.
2. The agent calls Analyze for authoritative facts.
3. The agent retrieves Analysis Presentation Guidance from EZT MCP.
4. The agent formats the findings into a concise brief with caveats.
5. Monica gets polished narrative insight without losing source-grounded facts.

---

## Map Component / Sharing Scenarios

### MC-000 — Brian gets a map visualization for development verification

1. A test fixture or tool run produces a TS with one or more TALs.
2. The agent calls `get_map_visualization` in `view` mode.
3. EZT MCP returns a browser/OpenClaw Canvas URL.
4. Brian verifies geometry and presentation visually before trusting downstream tool behavior.

### MC-001 — Monica opens a read-only map session in a browser

1. Monica says: "Give me a link to review this map."
2. The agent creates a read-only MC session for the active TAL.
3. EZT MCP returns a secure temporary browser URL.
4. Monica opens the URL and pans/zooms the map.
5. Monica can review but not edit the TS.

### MC-002 — Monica switches between TALs in the MC

1. Monica opens a TS with multiple TALs in the MC.
2. Monica uses the TAL switcher to change from one alignment to another.
3. The MC updates the displayed territories.
4. EZT MCP and the agent preserve the selected active TAL state.
5. Monica compares alternatives visually.

### MC-003 — Map session expires mid-session

1. Monica leaves a shared MC session open until it expires.
2. The MC reports that the session is no longer valid.
3. The agent detects the expiration.
4. The agent creates a fresh MC session from the current TS.
5. Monica resumes review with a new secure URL.

### MC-004 — Monica selects parts on the map and the agent realigns them

1. Monica opens a select-mode MC session.
2. Monica selects parts visually and clicks Done.
3. EZT MCP notifies the agent of the committed selection.
4. The agent uses the selection in a Realign request after Monica confirms the target territory.
5. The MC refreshes to show the updated TAL.

### MC-005 — Monica manually builds a new TAL by selecting ZIPs

1. Monica says: "I want to build a new territory layer manually from US ZIP codes."
2. The agent requests a first-class part-selection task for `us_zips` with purpose `build_territory`.
3. EZT MCP opens or reuses Monica's persistent MC workspace, displays the ZIP part layer, and switches the MC to select mode.
4. Monica ctrl-clicks, lassos, and boxes ZIPs until the first territory selection is ready.
5. Monica clicks Done.
6. EZT MCP commits the selected ZIP IDs and notifies the agent that the selection is available.
7. The agent asks Monica for the territory name and, for hierarchical TALs, the parent path such as Region/District.
8. Monica provides the territory metadata.
9. The agent calls a territory-from-parts mutation tool to create the territory in the new TAL.
10. EZT MCP updates the TS/TAL and pushes the refreshed TAL to the open MC.
11. Monica repeats selection and naming for the second territory, third territory, and so on until the manual TAL is complete.

Decision: Part selection is a first-class human spatial input workflow. The MC selects parts; the agent asks clarifying questions; EZT MCP mutation tools update the TS/TAL.

### MC-006 — Monica selects ZIPs and only wants the list

1. Monica says: "Let me select some ZIPs and give me the list when I'm done."
2. The agent requests a first-class part-selection task for `us_zips` with purpose `return_list`.
3. EZT MCP opens or reuses Monica's persistent MC workspace and switches the ZIP layer into select mode.
4. Monica selects ZIPs visually and clicks Done.
5. EZT MCP commits the selection and notifies the agent.
6. The agent retrieves the committed part selection and returns the ZIP list, optionally with labels or lightweight attributes.
7. No TS/TAL mutation is performed.

### MC-007 — Agent creates a narrative executive brief from TS and Analyze output

1. Monica says: "Summarize this plan for leadership."
2. The agent calls Analyze on the relevant TALs.
3. EZT MCP returns structured facts and caveats.
4. The agent uses presentation guidance to write an executive brief.
5. Monica receives a concise narrative with a map link and key numbers.

---

## Cache / Identity Scenarios

### CH-001 — Agent uses a TS cache handle across sequential calls

1. Monica works with a large TS.
2. The agent sends the TS to EZT MCP once and receives a short-lived cache handle.
3. The agent uses the handle for Analyze, Realign, and map-session creation.
4. EZT MCP resolves the handle for each call while it remains valid.
5. Monica gets faster sequential operations without changing the agent-owned storage model.

### CH-002 — Cache miss falls back to full TS resend

1. The agent tries to use a short-lived TS cache handle.
2. EZT MCP reports that the handle is expired or missing.
3. The agent falls back to resending the full TS from customer storage.
4. EZT MCP completes the requested operation.
5. Monica experiences a transparent recovery instead of a failed workflow.

---

## Future Point Location Update Scenarios

### PLU-001 — Monica corrects an account point location

1. Monica notices an account is geocoded to the wrong place.
2. Monica tells her agent: "Move this account to the correct location."
3. The agent identifies the point and the corrected coordinates or address.
4. EZT MCP updates the point location in the TS point layer.
5. The agent saves the corrected TS and warns Monica if downstream TALs may need rebuilding.

Decision: Point Location Update is post-MVP; Phase 1 handles corrected locations through re-ingestion or point-layer replacement.

---

## Scenario Backlog

- Teams meeting app / embedded MC workflow.
- Power BI formal reporting workflow.
- GeoJSON/table export interoperability workflow.
- Auth failure and API key rotation workflow.
- Long-running build progress notifications.
- Agent handoff between multiple MCP hosts.
