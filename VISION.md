Version: 0.8.0
Date: 2026-05-08
Status: Draft

EZT MCP is a server-side territory intelligence service that exposes EasyTerritory's core territory operations as MCP-native capabilities. It gives AI agents the ability to perform territory work that previously required a human expert inside EZT Designer.

Agents connect to EZT MCP to build, balance, analyze, share, and export territory solutions — using the same domain expertise that EasyTerritory has developed over a decade, encoded as an ExpertPack knowledge layer.

---

## The Problem

Territory planning today requires a trained user, EZT Designer, and significant manual iteration. The knowledge of what makes a good territory — contiguity, balance, workload equity, alignment to geographic units — lives in people's heads and in a client-side application.

Three problems follow from this:

- **Access barrier.** Territory design is expert work. Customers need trained users. Managers who know what they want cannot act on it without a specialist.

- **Integration friction.** Customers with existing alignment files, CRM exports, or external systems cannot easily bring that data into EZT without manual transformation.

- **No headless path.** There is no way to programmatically create or optimize territory solutions outside the Designer UI — no API, no batch pipeline, no agent interface.

EZT MCP eliminates all three.

---

## What Agents Can Do

A customer's AI agent — running OpenClaw, Claude Desktop, or any MCP-compatible host — connects to EZT MCP and can:

- Pull account data from the customer's CRM or data system, geocode it, and receive a Territory Solution carrying those records as a point layer
- Import an existing alignment file and receive a ready-to-consume Territory Solution carrying a territory alignment layer
- Build territories from scratch — from account groupings or from a target count with metric balancing; each build appends a new named TAL to the TS, enabling side-by-side comparison of multiple alignment strategies
- Realign an existing Territory Solution — directed by the user or by map widget selections
- Compare multiple Territory Alignment Layers in the Map Component — switch between TALs built with different metrics or strategies and run comparative analysis across them
- Analyze a Territory Solution — all account data and metrics are embedded in the TS, so no separate inputs are needed; Analyze can target one TAL or produce a cross-TAL comparison
- Present analysis clearly using EZT MCP-provided reporting guidance, templates, and presentation rules
- Persist Territory Solutions in the customer's own storage — EZT MCP returns results; the agent is responsible for saving and retrieving them
- Use short-lived TS cache handles to avoid repeatedly sending multi-MB territory geometries when calling several tools in sequence
- Share Territory Solutions with upper management through a flagship read-only map experience, including practical symbology/styling controls, Power BI-friendly exports, or agent-hosted narrative summaries
- Select geographic parts visually using an embedded Map Component (click, lasso, box) and direct the agent to realign them
- Understand the domain via an ExpertPack knowledge layer that encodes territory design expertise, EZT product knowledge, and guided workflows

The agent is not a thin API proxy. It is an expert system with hands. EZT MCP is a compute and knowledge service — it does not persist customer data. It may hold customer TS payloads transiently during request processing and in short-lived cache entries when the customer/agent opts into cache-assisted workflows.

---

## Who It Serves

EasyTerritory customers who run their own agents. EZT MCP is hosted by EasyTerritory and accessed by customers as a service — not a self-hosted product. Customers bring their MCP-compatible agent host; EZT MCP provides the territory intelligence layer.

Two primary interaction modes:

- **Assisted (designer present):** Agent works alongside a territory designer — handling geocoding, data ingestion, balance analysis, and solution creation while the human makes strategic decisions. Monica (a territory designer) uses the embedded map widget to select parts visually and instructs the agent to move them.
- **Conversational (manager-directed):** A sales manager or ops lead instructs the agent in natural language. The agent translates intent into geography and produces a territory solution without requiring a territory design specialist.

---

## MVP Tool Set

### 1. Geocode Address
Input: one or more address strings
Output: a Territory Solution (TS) with one point location layer and no territory alignment layer
Provider hierarchy: self-hosted Nominatim on the EZT MCP Resource Server → TomTom → Azure Maps fallback
Geocode results are cached in the Resource Server PostgreSQL database (address → lat/lon). Cache is non-customer-specific.

### 2. Direct Build — Alignment File → Territory Solution
Input: a CSV or Excel file mapping part identifiers to territory names; a named part layer (e.g., `us_zips`); an optional incoming TS to augment; a required `tal_label` naming the new TAL
Output: the TS with one new TAL appended; 0-N point layers are preserved from the incoming TS if supplied
Value: covers the most common onboarding scenario — customers migrating from spreadsheets, other tools, or manual systems
Note: Repair (hole-filling, contiguity) is applied internally when input data produces gaps. Direct Build always appends — it never replaces an existing TAL.

### 3. Account Build — Accounts with Grouping Attribute → Territory Solution
Input: account list with a grouping attribute (e.g., sales manager name, territory name) and account locations; a named part layer; an optional incoming TS to augment; a required `tal_label` naming the new TAL
Processing: two-stage pipeline:
- **Infer** — determine which parts each account resides in; group parts by the account's grouping attribute. When the grouping attribute is a part identifier (e.g., ZIP code on the account address), spatial inference is skipped and the mapping is direct — making Account Build functionally equivalent to Direct Build in that case.
- **Repair** — fill holes and restore contiguity in the resulting part assignments (swiss-cheese artifacts are common when accounts do not uniformly cover their intended geography)

Output: the TS with one new TAL appended; any point layers supplied by the caller or present in the incoming TS are preserved
Note: Repair is always applied internally; the output is always a topologically clean solution. Account Build always appends — it never replaces an existing TAL.

### 4. Auto Build — TS + Metric → Territory Solution
Input: a TS containing one or more point location layers with business metric fields, a named part layer, target territory count, optional constraints; a required `tal_label` naming the new TAL
Processing: three-stage pipeline:
- **Partition** — cluster accounts into N groups using a configurable metric (revenue, account count, workload hours)
- **Zone** — assign geographic parts to the nearest partition centroid using expanding spatial contours
- **Realign** — iteratively swap border parts between adjacent territories to minimize metric deviation while preserving contiguity

Output: an augmented TS with one new TAL appended over the requested part layer; all incoming point layers and any existing TALs are preserved
Note: the TS flows into and out of Auto Build. Auto Build always appends a new TAL — it never replaces an existing one. This makes it natural to run Auto Build multiple times against the same account data using different metrics or target counts and compare the resulting alignments side by side. The pipeline is informed by the existing EZT Designer auto-builder algorithm; PostGIS-native spatial operations on the Resource Server will be used where they materially improve performance or correctness.

### 5. Realign — Modify an Existing Territory Solution
Input: an existing TS; a `tal_id` identifying which TAL to modify; a set of realignment instructions (move these parts from territory A to territory B, or move these parts into a new territory)
Processing: reassign specified parts, re-dissolve affected territories, apply Repair to restore contiguity where needed
Output: updated TS with the specified TAL modified in place; all other TALs and point layers are preserved
Value: the most common ongoing operation — territory solutions drift as the business changes (new hires, lost accounts, growth in one region). Realign handles directed, explicit changes: splitting an oversized territory, absorbing a departed rep's territory, or moving a cluster of parts across a boundary.
Note: Realign handles *directed* changes (agent or user specifies what moves where). Auto Build's internal realign step handles *metric-driven* convergence during initial construction — these are distinct operations. When a TS carries multiple TALs, Realign always targets a specific TAL identified by `tal_id` — it never modifies all TALs at once.

### 6. Analyze Territory Solution
Input: a TS — point layers and their metric attributes are embedded in the TS itself; no separate account input required. Optional `tal_ids` parameter: a list of TAL ids to analyze. When omitted, all TALs in the TS are analyzed.
Output: structured JSON analysis — per-territory aggregates across all metric fields on all point layers, including comparisons, balance scores, outliers, exceptions, and suggested focus areas. When multiple TALs are analyzed, the output includes a cross-TAL comparison section: head-to-head balance scores, metric distribution differences, and recommended alignment given stated objectives. The JSON should contain everything a calling agent needs to reason accurately about the solution — or to help Monica decide which of two competing territory designs to commit to.
Note: this is the one tool whose output is not GeoJSON, since analysis results carry no geometry. Analysis against polygon area/perimeter is available when N=0 (no point layers), but metric analysis requires at least one point layer with flagged metric fields. Presentation guidance lives separately as an EZT MCP resource/prompt, not inside the tool output.

---

## Internal Operations

### Repair
Hole-filling and contiguity repair applied internally after Direct Build, Account Build, and Realign when part assignments produce gaps or disconnected geometry. Not exposed as a public MCP tool — it is a shared pipeline step. A future version may expose Repair as a public tool for customers who bring in territory solutions from external sources.

---

## Canonical Format — Territory Solution

A Territory Solution (TS) is the primary working artifact of EZT MCP. It is self-contained: it can carry a territory alignment layer, point location layers, both, or neither, along with enough metadata to support analysis and downstream sharing without external inputs.

**The TS is valid GeoJSON.** Specifically, it is a GeoJSON `FeatureCollection` with a conventions layer on top. No proprietary format, no custom binary, no EZT-specific file type. Any GeoJSON-aware tool can open and inspect a TS. The EZT MCP conventions (layer naming, `metric_fields`, `part_ids`, solution metadata) live in standard GeoJSON `properties` fields — they extend GeoJSON without breaking it.

The TS is always a GeoJSON `FeatureCollection`. A TS may contain point features, territory polygon features, both, or neither. Layer membership is declared in standard feature `properties` and summarized in the top-level metadata envelope. TALs are optional — Geocode Address returns a TS with point features but no TAL. A TS may carry multiple TALs simultaneously, enabling comparative territory analysis without creating separate files.

```json
{
  "type": "FeatureCollection",
  "properties": {
    "ezt_mcp_version": "1",
    "solution_name": "East Region 2026",
    "build_date": "2026-05-07",
    "ts_id": "ts_01HX7E9Q4K8Z3M2N6P5R1A0B7C",
    "revision": 5,
    "content_hash": "sha256:9f2c...",
    "updated_at": "2026-05-07T15:00:00Z",
    "part_layer": "us_zips",
    "active_tal_id": "tal_revenue",
    "layers": [
      {
        "id": "tal_revenue",
        "kind": "territory_alignment",
        "label": "By Revenue Q1",
        "feature_role": "territory",
        "part_layer": "us_zips",
        "part_id_property": "zip"
      },
      {
        "id": "tal_headcount",
        "kind": "territory_alignment",
        "label": "By Headcount",
        "feature_role": "territory",
        "part_layer": "us_zips",
        "part_id_property": "zip"
      },
      {
        "id": "accounts",
        "kind": "point",
        "feature_role": "location",
        "metric_fields": ["annual_revenue", "account_count"]
      }
    ],
    "presentation": {
      "active_view": "executive_review",
      "views": [
        {
          "id": "executive_review",
          "label": "Executive Review",
          "layers": {
            "tal_revenue": {
              "visible": true,
              "fill": { "type": "categorical", "property": "territory_id", "palette": "ezt_distinct" },
              "stroke": { "color": "#ffffff", "width": 1.5 },
              "opacity": 0.72,
              "label": { "property": "name", "min_zoom": 5 }
            },
            "tal_headcount": {
              "visible": false,
              "fill": { "type": "categorical", "property": "territory_id", "palette": "ezt_distinct" },
              "stroke": { "color": "#ffffff", "width": 1.5 },
              "opacity": 0.72,
              "label": { "property": "name", "min_zoom": 5 }
            },
            "accounts": {
              "visible": true,
              "symbol": { "shape": "circle", "size": 5, "color": "#334155" }
            }
          }
        }
      ]
    }
  },
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "MultiPolygon", "coordinates": ["..."] },
      "properties": {
        "layer_id": "tal_revenue",
        "feature_role": "territory",
        "territory_id": "north",
        "name": "Territory North",
        "group": "East Region",
        "part_ids": ["12345", "12346", "12347"]
      }
    },
    {
      "type": "Feature",
      "geometry": { "type": "MultiPolygon", "coordinates": ["..."] },
      "properties": {
        "layer_id": "tal_headcount",
        "feature_role": "territory",
        "territory_id": "north",
        "name": "Territory North",
        "group": "East Region",
        "part_ids": ["12345", "12348", "12349"]
      }
    },
    {
      "type": "Feature",
      "geometry": { "type": "Point", "coordinates": [-81.52, 30.33] },
      "properties": {
        "layer_id": "accounts",
        "feature_role": "location",
        "name": "Acme Corp",
        "annual_revenue": 142500.00,
        "account_count": 1
      }
    }
  ]
}
```

Key rules:
- **Valid GeoJSON throughout.** A TS is a GeoJSON `FeatureCollection`. All geometry follows the GeoJSON spec (RFC 7946). Any standard GeoJSON library can parse it.
- A TS may contain **0-N point location layers**. Point layers are optional. Geocode Address returns a TS with one point layer and no TAL.
- A TS may contain **0-N territory alignment layers (TALs)**. TALs are optional and multiple TALs may coexist in the same TS. Each TAL is independently named and identified. This is the foundation of comparative territory analysis: Monica can build two alignments using different metrics, switch between them in the Map Component, and run Analyze across both before committing to one.
- The `active_tal_id` field in top-level properties identifies which TAL the Map Component renders by default. The agent may set or update this field as the user switches between alignments.
- When present, each TAL territory feature carries **dissolved polygon geometry** — the union of all its constituent parts. `part_ids` records composition.
- Each TAL records the `part_layer` it was built from (for example, `us_zips`) so Realign and Analyze operations know which atomic geography underlies it. Multiple TALs in the same TS may use different part layers.
- Each point layer declares `metric_fields` — the attribute names that Analyze should aggregate. Non-metric attributes are carried through but not analyzed.
- The TS is the single artifact that flows through the pipeline: geocode → build → add layers → auto-build → realign → analyze → style → share. Tools should adorn/augment the incoming TS rather than forcing callers to manage separate geometry artifacts.
- Build tools (Direct Build, Account Build, Auto Build) always **append** a new TAL — they never replace or modify existing TALs. The agent removes unwanted TALs after the user decides which alignment to keep. This is a deliberate constraint: the system of record for territory decisions is the agent, not EZT MCP.
- **The customer's agent owns durable TS storage.** EZT MCP does not persist TS files as a system of record. Every tool call can pass the current TS in and receive an updated TS back. For efficiency, tools may also accept a short-lived TS cache handle instead of the full payload. The agent is still responsible for durable saving, retrieval, and pulling account data from the customer's source systems.

---


## TS Identity and Short-Lived Cache Handles

TS files can become large because dissolved polygon territories and point layers may be several MBs. To reduce bandwidth, latency, and repeated serialization costs, every TS should carry identity and revision metadata:

- `ts_id` — stable unique identifier for the logical TS
- `revision` — monotonically increasing integer or comparable version marker
- `content_hash` — deterministic hash of the canonicalized TS payload, e.g. SHA-256
- `updated_at` — ISO timestamp for the current revision

EZT MCP may support a short-lived in-memory or distributed cache for TS payloads. The workflow:

1. Agent sends a full TS or asks whether a `ts_id`/`content_hash` is already cached.
2. EZT MCP returns a cache hit/miss and, on hit, a short-lived `ts_handle`.
3. Subsequent tool calls may pass `ts_handle` instead of the full TS payload.
4. Any tool that changes the TS returns updated identity metadata and either the full TS or a new cache handle, depending on caller preference.

This is a transport optimization, not durable storage. Cache entries must be encrypted or memory-resident according to deployment policy, customer/API-key scoped, TTL-bound, size-limited, and explicitly non-authoritative. A cache miss must never break the workflow; the agent can always resend the full TS.

The product claim should therefore be precise: EZT MCP does **not persist** customer TS files or act as their system of record. It may transiently hold customer data for request processing and short-lived cache-assisted workflows.

## Resource Server and Part Layers

EZT MCP is backed by an EasyTerritory-hosted **Resource Server**: a PostgreSQL/PostGIS instance that provides shared spatial resources and compute support for the stateless MCP tier. It is not customer storage. It contains curated part geometry layers, self-hosted Nominatim data, US reference datasets, geocode cache tables, and spatial indexes/functions used when computation is better executed close to the geometry.

Part layers are EasyTerritory's curated geographic datasets — the result of years of curation and refinement. Part layers are stored in PostgreSQL/PostGIS on the Resource Server and hosted by EasyTerritory.

Available layers in v1: US ZIP codes, US counties, US states, Canadian FSAs. Additional layers are an operational concern.

Callers reference part layers by name (e.g., `"us_zips"`). EZT MCP resolves geometries internally and records the selected part layer in the TS/TAL metadata.

### Basemap and PMTiles Delivery

The Resource Server is not the basemap tile store. Basemap and browser delivery artifacts should be generated as separate derived outputs from the same source datasets and hosted as static files.

Recommended model:

- **Same OSM source extract, separate derived outputs.** A US OSM extract can feed both Nominatim import and OSM-derived basemap tile generation, but the Nominatim geocoder schema is not the cartographic source of truth.
- **Resource Server PostgreSQL/PostGIS** holds Nominatim/geocoder data, `geocode_cache`, curated `shared_geo` part layers, and approved spatial helper functions.
- **PMTiles build pipeline** produces vector PMTiles archives for the Map Component: OSM-derived basemap PMTiles from Protomaps/Planetiler-style processing, plus part-layer PMTiles generated from canonical `shared_geo` tables.
- **Blob/object storage** is the natural home for PMTiles archives. They are static, read-only delivery artifacts served over HTTPS with HTTP Range Request support — not tables inside PostgreSQL and not customer data storage.
- **TS GeoJSON remains the customer solution artifact.** Customer-specific territory solutions are rendered by the Map Component as TS/GeoJSON supplied by the agent, not baked into basemap PMTiles for v1.

This separates responsibilities cleanly: PostGIS is canonical for geocoding, shared spatial computation, and curated part geometries; PMTiles is optimized browser delivery for basemap and part-boundary rendering.

---

## Infrastructure Model

EasyTerritory hosts all infrastructure. Customers are not responsible for deployment.

- **EZT MCP server** — stateless; hosted by EasyTerritory
- **Resource Server: PostgreSQL (PostGIS)** — hosted by EasyTerritory in Azure; contains part layers, self-hosted Nominatim + US reference data, geocode cache, spatial indexes/functions, and no customer-specific territory data
- **PMTiles/object storage** — vector basemap PMTiles and part-layer PMTiles are static browser-delivery artifacts hosted outside PostgreSQL, ideally in Azure Blob Storage or equivalent object storage with Range Request support
- **Customer's agent** — owns all customer-specific data: Territory Solutions, account lists, alignment files. Pulls account data from source systems (CRM, spreadsheets, databases). Persists TS files between sessions. Passes TS into EZT MCP on each call; receives the updated TS back.
- **Auth** — API key per customer; Bearer token on every request

EZT MCP is stateless in the durable-storage sense beyond shared Resource Server data and optional short-lived TS cache entries. It never writes customer TS files to persistent storage as a system of record. The agent is the custodian of all customer artifacts.

---



## Product Design System — DESIGN.md

EZT MCP should include a repo-level `DESIGN.md` file that captures the visual language of EZT Designer V2 for AI coding agents. This mirrors the emerging DESIGN.md pattern: machine-readable design tokens in YAML frontmatter plus human-readable rationale and component guidance in Markdown. The goal is to let agents build UI that feels native to the EasyTerritory product stack.

Benton's EZT Designer V2 work is the source of truth. Benton or Benton's agent should extract colors, typography, spacing, component patterns, map legend behavior, callouts, controls, and map-specific states from Designer V2 and populate `DESIGN.md`. The EZT MCP Map Component should consume those tokens/guidelines for product chrome and default styling.

`DESIGN.md` is distinct from TS presentation metadata:

- `DESIGN.md` defines the EasyTerritory product look and component language.
- TS presentation metadata defines solution-specific map styling: territory colors, classifications, labels, legends, named views.

Together they keep the Map Component both product-consistent and solution-aware.

## Comparative Territory Analysis

When a TS carries multiple TALs, the Map Component and Analyze tool together enable a full comparison workflow:

1. Monica asks the agent to build a territory alignment optimized for revenue balance.
2. The agent runs Auto Build with metric `annual_revenue` and `tal_label: "By Revenue"` — the TS now has one TAL.
3. Monica asks for a second alignment optimized for account count equity.
4. The agent runs Auto Build again with metric `account_count` and `tal_label: "By Headcount"` — the TS now has two TALs.
5. The Map Component TAL switcher lets Monica toggle between "By Revenue" and "By Headcount" overlaid on the same point data.
6. Monica asks the agent to compare them. The agent calls Analyze with both `tal_ids` — the response includes cross-TAL balance scores, metric distribution differences, and a recommendation.
7. Monica picks "By Revenue." The agent removes the `tal_headcount` TAL, updates `active_tal_id`, and persists the TS.

This workflow requires no new tools. The multi-TAL TS structure, the `tal_id` parameter on Realign and Analyze, and the `active_tal_id` field on the Map Component are sufficient.

---

## Map Styling and Symbology

A lightweight Map Component still needs serious styling support. EZT Designer has many mature concepts here — layer visibility, symbology, color classification, symbol classification, graduated symbols, labels, filters, legends, and saved visualization configurations. EZT MCP should not attempt to reproduce the entire Designer styling surface in v1, but it must provide enough styling control for read-only sharing, verification, and agent-assisted review to be useful.

Recommended model: **style lives with the TS as portable presentation metadata**, with optional reusable style templates supplied by EZT MCP.

- The TS remains valid GeoJSON. Styling is stored in `properties.presentation` / layer metadata, not in a proprietary sidecar format.
- Styles are declarative, not imperative: layer visibility, fill/stroke colors, opacity, labels, legend entries, classification rules, symbol sizes, and metric-driven thematic coloring.
- The Map Component renders this style spec consistently in `view` and `select` modes.
- Agents can ask EZT MCP for recommended styles based on context: executive review, balance diagnostic, territory comparison, account coverage, QA verification.
- EZT MCP may expose style templates/resources such as `default_territory_style`, `analysis_variance_style`, or `executive_review_style`.
- If a TS lacks explicit style metadata, the Map Component applies safe defaults: distinct territory colors, readable boundaries, optional labels, and a generated legend.

V1 should support a compact subset:

1. Territory fill/stroke/opacity, with deterministic distinct colors by territory
2. Territory labels from a configured property, usually territory name
3. Point layer visibility and simple symbol styling
4. Metric classification for point layers and TAL summaries: equal interval, quantile, manual breaks, categorical unique values
5. Legend generation from the active style spec
6. Saved named visualization presets inside the TS metadata

This gives the shared map enough expressiveness without turning it into Designer. Advanced Designer styling — full symbology editor, complex filters, hotspots, clustering, print layouts, and deep layer-management workflows — can remain out of scope until the Functional/Technical Spec proves they are needed.

## Analysis Presentation Guidance

The Analyze Territory Solution tool returns structured JSON facts, not prose. That is deliberate: the tool output should be complete, deterministic, and easy for agents to inspect. But raw JSON is not enough. EZT MCP should also provide a polished agent-facing presentation resource — conceptually `ANALYSIS_DESIGN.md`, `analysis_style`, or an MCP resource/prompt — that tells calling agents how to turn analysis JSON into useful operator insight.

This guidance should include:

- Recommended executive summary structure: what changed, whether the solution is balanced, biggest exceptions, recommended decisions
- Metric interpretation rules: how to explain variance, balance scores, territory outliers, whitespace, workload, and account concentration
- Visual presentation rules: when to use bullets, tables, charts, map callouts, and territory ranking
- Audience modes: executive readout, territory designer diagnostic, sales manager action list, QA/verification report
- Caveats and uncertainty language: distinguish computed facts from recommendations, and avoid overclaiming causality
- Follow-up prompts: questions the agent should ask when the analysis reveals ambiguity or tradeoffs

The goal is not to make EZT MCP generate every narrative itself. The goal is to ship EasyTerritory's opinionated analysis presentation expertise alongside the compute result, so any capable calling agent can produce a polished, helpful, and domain-appropriate explanation.

This should be treated as part of the product surface. Analysis quality is not just calculation accuracy — it is whether the human operator can quickly understand what matters and what to do next.

## Sharing Territory Solutions

Sharing a TS is a flagship feature, not an afterthought. EasyTerritory customers already share territory solutions with upper management, including through read-only Designer users and Power BI integrations. Agentic workflows may reduce some handoff friction over time, but humans-in-the-loop will remain important for quite a while. Executives, sales leaders, and operations teams need to see and interact with a TS without becoming territory editors.

Recommended v1 sharing model:

1. **Agent-owned TS file** — the agent stores the canonical TS in the customer's chosen storage location. This remains the source of truth.
2. **Unified Map Component, mode-switched** — the same map component renders a styled TS in both read-only sharing contexts and assisted editing/selection contexts. Capabilities are enabled or disabled by mode:
   - `view` mode: pan, zoom, inspect, toggle layers, view labels/metrics, no changes emitted
   - `select` mode: view plus part selection output for agent-directed Realign
   - future `edit` mode: richer editing if/when warranted, still mediated by the agent and MCP tools
3. **Read-only executive sharing** — the agent can generate or launch a read-only map view from a TS for upper management: territories, key metrics, labels, optional point overlays, and a simple legend. This is the MCP-era equivalent of a read-only Designer consumption path.
4. **Power BI-friendly path** — because EasyTerritory already has Power BI integration, EZT MCP should be able to export or project the TS into Power BI-consumable GeoJSON/table outputs when the customer wants a dashboard rather than an agent-hosted map.
5. **Narrative briefing** — the agent should be able to generate an executive summary from the TS + Analyze output: what changed, balance scores, exceptions, and recommended follow-up decisions.

This creates three management consumption modes without introducing a new system of record: interactive read-only map, Power BI dashboard, and narrative summary. The read-only map and assisted map widget should be the same underlying component with capability flags, not two separate products.

## ExpertPack Knowledge Layer

EZT MCP is backed by an ExpertPack — a structured knowledge file set encoding:

- Territory design principles (contiguity, balance, workload equity, geographic unit selection)
- EZT product knowledge (Designer concepts, project structure, terminology)
- Workflow guidance (how to approach common territory problems, what questions to ask, what constraints matter)
- EZT MCP tooling knowledge (when to use which tool, how to chain operations, how to interpret results)

This ExpertPack is new — not a copy of the existing `ezt-designer` pack. It emphasizes operational and workflow knowledge alongside product knowledge, with a customer-facing lens rather than an internal implementation lens.

The retrieval layer uses the same hybrid search pipeline (BM25 + vector, intent-aware routing, `requires:` expansion) proven at 97.6% retrieval accuracy in production on EP MCP.

---

## What This Is Not

- Not a SaaS product with a full territory-management UI — it is an MCP server for agent access plus a flagship, lightweight TS viewing/sharing surface
- Not a replacement for EZT Designer — it produces and modifies territory solutions; the Designer remains the visual editing surface
- Not a durable customer data store — EZT MCP does not persist, retrieve, or manage customer Territory Solutions, account data, or alignment files as a system of record. The customer's agent owns all of that. Short-lived cache handles are a transport optimization, not durable storage.
- Not a proprietary format — the TS is standard GeoJSON; no EZT-specific file type or SDK is required to read it
- Not multi-tenant in the database sense — the Resource Server holds only shared spatial infrastructure; no per-customer rows
- No standalone Designer replacement — the unified map component provides read-only viewing and agent-mediated selection/editing, but Designer remains the full power-user surface (see MAP_COMPONENT.md)
- No in-place mutation of existing Designer projects in v1 — EZT MCP builds and returns new solutions

---

## Lifecycle

This project follows a waterfall lifecycle:

- Vision ← you are here
- Constitution — non-negotiables: architecture, stack, security, coding conventions, deployment model
- Functional Spec — behavior definition: tools, resources, prompts, canonical format schema, error handling
- Technical Spec — architecture and design: module breakdown, data flow, retrieval pipeline, API surface
- Implementation — execution
- Verification — QA, test vectors, eval sets

EZT MCP forks from `brianhearn/ep-mcp`. The EP MCP retrieval engine is retained as the knowledge layer backbone. EZT-specific tools (build, geocode, realign, analyze) are added on top.

The map widget (see MAP_COMPONENT.md) is a companion component — not part of the MCP server itself. It is an embeddable spatial I/O surface delivered inside the agent host.

---

*This document is the product intent record for EZT MCP. It will not be updated as implementation proceeds — deviations are tracked in CHANGELOG.md. The Constitution, Functional Spec, and Technical Spec are the authoritative downstream artifacts.*
