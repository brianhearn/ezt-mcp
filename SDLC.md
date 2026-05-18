# SDLC.md — EZT MCP Documentation Model

**Version:** 0.1.5
**Date:** 2026-05-17
**Status:** Draft — documentation governance

This document defines the repository's SDLC documents and their boundaries. The goal is to keep each document useful, current, and non-redundant. When adding or editing docs, put information in the one document that owns it and link to that document from elsewhere instead of copying details.

---

## Documentation Principles

1. **One source of truth per fact.** If a fact has a natural owner, write it there and link to it elsewhere.
2. **Current state only in core docs.** Core docs describe the latest agreed state, not decision history. Change history belongs in `CHANGELOG.md`.
3. **No narrative archaeology.** Do not write “we used to do X, then changed to Y” in README, Vision, Constitution, specs, or schemas. Capture that in `CHANGELOG.md` if it matters.
4. **Specs become more concrete as they move downstream.** Vision says why/what. Constitution says non-negotiables. Functional Spec says behavior. Technical Spec says implementation design.
5. **Scenarios drive specs, not the reverse.** Use `SCENARIOS.md` to discover requirements and edge cases before locking tool/resource contracts.
6. **README summarizes and routes.** README should remain short and point readers to the authoritative docs.
7. **Executable contracts beat prose when possible.** Schemas, examples, and test vectors should live beside the spec they validate or in dedicated schema/test directories referenced by the spec.

---

## SDLC Document Set

### `README.md` — Project entry point

**Purpose:** orient a new reader quickly.

**Owns:**
- one-paragraph project summary
- high-level capability list
- architecture summary at navigation depth only
- lifecycle/status table
- links to authoritative docs
- setup/dev quickstart once implementation begins

**Does not own:**
- detailed product rationale
- non-negotiable architecture rules
- tool schemas or resource contracts
- scenario details
- implementation design
- decision history

**Rule of thumb:** if a README section grows beyond a brief summary, move the detail to its owning doc and link it.

---

### `VISION.md` — Product intent and scope

**Purpose:** explain why EZT MCP exists, who it serves, and what the product is trying to accomplish.

**Owns:**
- problem statement
- target users / interaction modes
- product capabilities at conceptual level
- MVP product scope
- what the product is not
- high-level sharing/reporting/product positioning
- canonical product terminology when it is needed to understand intent

**Does not own:**
- exact MCP tool input/output schemas
- resource URI/event contracts
- implementation priority except where visual verification is needed before downstream tool development
- module layout
- detailed security rules
- test strategy
- implementation choices beyond product-relevant architecture

**Rule of thumb:** Vision should convince and align. It should not be precise enough to implement from.

---

### `CONSTITUTION.md` — Non-negotiables and constraints

**Purpose:** define the rules downstream work must obey unless the Constitution is explicitly revised.

**Owns:**
- locked stack choices
- architecture non-negotiables
- security non-negotiables
- canonical format constraints
- coding/dependency/deployment constraints
- testing/deployment requirements that are mandatory across the project

**Does not own:**
- happy-path workflows
- detailed tool behavior
- endpoint/resource payload schemas, except as constraints
- product rationale already covered by Vision
- implementation module details beyond required conventions

**Rule of thumb:** Constitution says “must/must not.” It should not read like a functional spec.

---

### `SCENARIOS.md` — Workflow scenario collection

**Purpose:** capture realistic human/agent/EZT MCP workflows before freezing specs.

**Owns:**
- end-to-end user scenarios
- actors, starting state, intent, happy path
- expected agent behavior
- capabilities exercised
- Map Component behavior, including visual verification loops
- state/revision/identity concerns surfaced by scenarios
- failure and edge cases
- design conclusions and open questions discovered from scenarios

**Does not own:**
- final tool schemas
- final resource contracts
- implementation design
- normative security policy except scenario-specific concerns

**Rule of thumb:** scenarios may mention candidate tools/resources, but they do not define final contracts. Once a contract is accepted, move it to `FUNCTIONAL_SPEC.md` and leave scenarios as examples.

---

### `FUNCTIONAL_SPEC.md` — Behavioral contract

**Purpose:** define what EZT MCP does from the outside, independent of implementation internals.

**Owns:**
- MCP tools, resources, prompts, and expected host interactions
- tool/resource/prompt inputs and outputs
- TS behavior rules from a caller perspective
- Map Component modes and external event behavior
- errors, validation, permissions, and edge-case behavior
- lifecycle/state-machine behavior for live sessions
- visual verification behavior for geometry-producing workflows
- accepted layer-legend behavior from a caller/user perspective: layer visibility, classification toggles, simple filter state, legend semantics, and how point location layers in the TS are exposed in MC sessions
- examples sufficient for client/agent implementers
- acceptance criteria at behavior level

**Does not own:**
- Python module structure
- database schema details except externally observable effects
- algorithm implementation details beyond behavioral guarantees
- infrastructure deployment mechanics
- historical rationale

**Rule of thumb:** an agent/client developer should be able to integrate from the Functional Spec without knowing the internals.

---

### `TECHNICAL_SPEC.md` — Implementation design

**Purpose:** explain how the Functional Spec will be implemented.

**Owns:**
- service/module architecture
- internal data flow
- database tables/functions/migrations
- cache/session implementation
- auth/audit implementation
- algorithm choices and internal pipelines
- deployment topology details
- performance/scaling considerations
- observability/logging design
- test implementation strategy
- current implementation notes and known hardening gaps when they affect how future agents should continue work

**Does not own:**
- product intent
- user-facing workflow prose except references to scenarios/spec sections
- canonical external contracts already owned by Functional Spec
- changelog/history
- long-form work logs or handoff notes that belong in memory/session-state or CHANGELOG

**Rule of thumb:** if changing it would not require a client/agent behavior change, it probably belongs in Technical Spec, not Functional Spec.

---

### `MAP_COMPONENT.md` — Map Component concept and UX contract

**Purpose:** define the companion Map Component as a product/UX surface, especially where it interacts with agents and EZT MCP.

**Owns:**
- Map Component role and boundaries
- modes: `view`, `select`, future `edit`
- UX primitives and expected behavior
- rendering expectations, including active/dimmed TAL behavior at the UX level
- customer-facing MC vocabulary, chrome-label intent, and localization/i18n expectations at the UX level
- embedding targets
- browser communication model at conceptual level
- product/UX open questions
- layer-legend UX requirements at the conceptual level: integrated layer visibility plus legend rows, point-layer filtering/classification expectations, and which Designer patterns should inform MC behavior before contracts are finalized

**Does not own:**
- final MCP resource schemas or event payloads once Functional Spec exists
- detailed MapLibre implementation
- authoritative TS schema
- concrete `presentation.chrome_labels` payload shape after Functional/Technical Spec define it
- general sharing/reporting strategy except as it affects Map Component

**Rule of thumb:** Map Component explains the human-facing spatial surface. Functional Spec owns exact external contracts.

---

### `DESIGN.md` — EasyTerritory design system for agents

**Purpose:** provide AI-codable design guidance for product chrome and visual consistency.

**Current status:** v0.2.0 is populated from Benton's EZT Designer V2 extraction and is the canonical visual source for the EZT MCP Map Component.

**Owns:**
- visual tokens
- typography, spacing, color, and component language
- buttons, panels, legends, empty/error/loading states
- map callouts and UI patterns
- Map Component chrome variants and map-specific visual states
- Layer-Legend visual pattern: compact rows, icons/swatches, visibility affordances, classification sub-rows, disabled/out-of-scale states, and spacing/color treatment
- design rationale and constraints

**Does not own:**
- TS presentation metadata schema except design guidance
- layer/filter/classification behavior contracts
- workflow behavior
- MCP contracts
- product scope

**Rule of thumb:** DESIGN.md tells an implementation agent how the UI should look and feel, not what the product does. Implementation agents building UI must read it before editing Map Component code.

---

### `ANALYSIS_DESIGN.md` — Analysis presentation guidance

**Purpose:** teach agents how to turn Analyze JSON into useful human-facing insight.

**Owns:**
- executive summary patterns
- territory designer diagnostic patterns
- sales manager action-list patterns
- QA/verification report patterns
- caveat and uncertainty language
- grid/table/chart guidance
- example analysis narratives

**Does not own:**
- Analyze tool schema
- analysis computation rules
- Map Component rendering rules
- general product vision

**Rule of thumb:** Analyze returns facts; ANALYSIS_DESIGN explains how an agent should present those facts.

---

### `CHANGELOG.md` — Change history

**Purpose:** record notable changes over time.

**Owns:**
- versioned change entries
- date-stamped additions/changes/removals
- brief rationale when useful
- links/references to changed docs

**Does not own:**
- current authoritative product behavior
- detailed specs
- long-form rationale

**Rule of thumb:** if a core doc changes, update CHANGELOG. Do not copy changelog history back into the core doc.

---

## Future / Optional Artifacts

### `schemas/`

**Purpose:** machine-readable contracts.

Potential contents:
- TS JSON Schema
- MCP tool input/output JSON Schemas
- resource/event payload schemas
- example payloads and test vectors

**Owner relationship:** schemas are authoritative for structure; `FUNCTIONAL_SPEC.md` explains behavior and links to schemas.

### `examples/`

**Purpose:** concrete sample TS files, tool requests/responses, and scenario payloads.

**Owner relationship:** examples illustrate specs; they do not define behavior on their own.

### `TEST_PLAN.md` or `tests/README.md`

**Purpose:** verification strategy once implementation begins.

**Owner relationship:** Functional Spec defines acceptance behavior; Technical Spec/Test Plan defines how it is tested.

---

## Source-of-Truth Matrix

| Topic | Authoritative doc |
|---|---|
| Project summary/navigation | `README.md` |
| Product why/scope | `VISION.md` |
| Non-negotiable constraints | `CONSTITUTION.md` |
| User workflows and edge cases | `SCENARIOS.md` |
| MCP tools/resources/prompts behavior | `FUNCTIONAL_SPEC.md` |
| Exact external payload structure | `FUNCTIONAL_SPEC.md` + `schemas/` when present |
| Internal implementation design | `TECHNICAL_SPEC.md` |
| Map Component role/UX concept | `MAP_COMPONENT.md` |
| Map Component browser/session implementation | `TECHNICAL_SPEC.md` |
| UI visual language | `DESIGN.md` |
| Analysis narrative/presentation | `ANALYSIS_DESIGN.md` |
| Change history | `CHANGELOG.md` |

---

## Editing Checklist

Before adding or editing documentation:

1. Identify the source-of-truth owner for the fact.
2. Put detailed content only in that owner doc.
3. In other docs, add a short summary plus link if needed.
4. Do not duplicate schemas, examples, or long workflows across docs.
5. If a core decision changes, update the owning doc and `CHANGELOG.md`.
6. If a scenario graduates into a contract, move the normative behavior to `FUNCTIONAL_SPEC.md` and keep `SCENARIOS.md` as illustrative.
7. Run a quick grep for duplicated terms/sections if the change affects multiple docs.

---

## Naming Conventions

Use stable, boring names:

- `README.md`
- `VISION.md`
- `CONSTITUTION.md`
- `SCENARIOS.md`
- `FUNCTIONAL_SPEC.md`
- `TECHNICAL_SPEC.md`
- `MAP_COMPONENT.md`
- `DESIGN.md`
- `ANALYSIS_DESIGN.md`
- `CHANGELOG.md`

Avoid creating overlapping alternatives such as `ARCHITECTURE.md`, `PRODUCT.md`, `REQUIREMENTS.md`, or `NOTES.md` unless a future need is clearly distinct from the ownership model above.

---

## Current Guidance for Next Phase

The immediate next phase is implementation hardening around the now-working Direct Build / Map Component testbed. Preserve the external v1 contracts while tightening internals. Current priorities:

- keep `get_map_visualization` as the stable public tool name for read-only/share/select map visualization;
- maintain MC visual smoke coverage for every deploy that touches job, map-session, progress, CSS, render-payload, layer-legend, point-layer rendering, classification/filter handling, or part-layer overlay paths; use `scripts/create_point_range_demo.py` for a reusable point-layer range-class demo when browser/user visual feedback is needed;
- run `scripts/smoke_direct_build.py --base-url https://expertpack.ai/mcp` for deploys touching Direct Build, queued jobs, PostGIS geometry fetch/dissolve, TAL metadata, Map Component render-payload creation, or part-layer overlay metadata;
- preserve the headless presentation model for point layers: Monica/the agent configures point-layer style, filters, and classification in TS presentation metadata; the MC renders the resolved configuration and class toggles but must not become a full symbology/query editor; next UI refinement should improve long layer-label wrapping/truncation, class-row spacing, and request-level custom-content plumbing;
- preserve the session-scoped part-layer model: each map session may expose one or more customer/workflow-valid part layers, but selection semantics are mutually exclusive through `active_part_layer`; selection commits must include both `part_layer` and `part_ids`;
- use `scripts/build_part_layer_pmtiles_tippecanoe.py` as the preferred operational builder for z9+ part-layer PMTiles. The live `us_zips.pmtiles` overlay is now a tippecanoe-built z5-z12 archive from canonical PostGIS `geo.us_postal`; future part-layer tile work should reuse that pipeline before considering custom Python tiling;
- keep transient queue details in `TECHNICAL_SPEC.md`, not in Functional Spec unless caller-visible behavior changes;
- keep migration/operator status in `CHANGELOG.md` and memory/session-state, not scattered across core docs;
- migration 003 (`migrations/003_job_payloads_limits.sql`) is **live** as of 2026-05-18. The pre-migration compatibility fallback has been removed (`33781bd`). The hardened `transient.job_payloads` + attempt/backoff path is now the only implementation. No further migration scaffolding exists to clean up.

External contracts to preserve:

- TS input/output behavior
- `get_map_visualization` as the stable public tool name for read-only/share/select map visualization
- selection/state resources
- Analyze `scope`
- Realign with optimistic concurrency and map refresh
- sharing guidance prompts/resources
- Power BI/export lane

Do not create a parallel `share_map_view` tool unless a future scenario proves it needs a distinct contract; S002 should use `get_map_visualization` in `view` mode.
