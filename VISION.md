Version: 0.3.0
Date: 2026-05-05
Status: Draft

EZT MCP is a server-side territory intelligence service that exposes EasyTerritory's core territory operations as MCP-native capabilities. It gives AI agents the ability to perform territory work that previously required a human expert inside EZT Designer.

Agents connect to EZT MCP to build, balance, analyze, and export territory solutions — using the same domain expertise that EasyTerritory has developed over a decade, encoded as an ExpertPack knowledge layer.

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

- Import an existing alignment file (ZIP-to-territory CSV/Excel mapping ZIP codes to territory names) and receive a ready-to-consume territory solution as GeoJSON
- Build from account data — provide a list of accounts with locations and a business metric, specify a target territory count, and receive an auto-balanced solution as GeoJSON
- Geocode addresses as a first-class operation
- Analyze a territory solution against a set of accounts and business metrics, receiving per-territory comparisons (e.g., total revenue, account count, balance score)
- Understand the domain via an ExpertPack knowledge layer that encodes territory design expertise, EZT product knowledge, and guided workflows

The agent is not a thin API proxy. It is an expert system with hands.

---

## Who It Serves

EasyTerritory customers who run their own agents. EZT MCP is hosted by EasyTerritory and accessed by customers as a service — not a self-hosted product. Customers bring their MCP-compatible agent host; EZT MCP provides the territory intelligence layer.

Two primary interaction modes:

- **Assisted (designer present):** Agent works alongside a territory designer — handling geocoding, data ingestion, balance analysis, and solution creation while the human makes strategic decisions
- **Conversational (manager-directed):** A sales manager or ops lead instructs the agent in natural language. The agent translates intent into geography and produces a territory solution without requiring a territory design specialist

---

## MVP Tool Set

### 1. Geocode Address
Input: one or more address strings
Output: a GeoJSON `FeatureCollection` of `Point` features, each with the original address in `properties`
Provider hierarchy: Nominatim (where ToS permits) → TomTom → Azure Maps fallback
Geocode results are cached in a shared PostgreSQL table (address → lat/lon). Cache is non-customer-specific.

### 2. Direct Build — Alignment File → Territory Solution
Input: a CSV or Excel file mapping ZIP codes to territory names; a named part layer (e.g., `us_zips`)
Output: a territory solution `FeatureCollection` (see Canonical Format below)
Value: covers the most common onboarding scenario — customers migrating from spreadsheets, other tools, or manual systems
Note: Repair (hole-filling, contiguity) is applied internally when input data produces gaps.

### 3. Account Build — Accounts with Grouping Attribute → Territory Solution
Input: account list with a grouping attribute (e.g., sales manager name, territory name) and account locations; a named part layer
Processing: two-stage pipeline:
- **Infer** — determine which parts each account resides in; group parts by the account's grouping attribute. When the grouping attribute is a part identifier (e.g., ZIP code on the account address), spatial inference is skipped and the mapping is direct — making Account Build functionally equivalent to Direct Build in that case.
- **Repair** — fill holes and restore contiguity in the resulting part assignments (swiss-cheese artifacts are common when accounts do not uniformly cover their intended geography)

Output: a territory solution `FeatureCollection`
Note: Repair is always applied internally; the output is always a topologically clean solution.

### 4. Auto Build — Accounts + Metric → Territory Solution
Input: account list (locations + business metric), named part layer, target territory count, optional constraints
Processing: three-stage pipeline:
- **Partition** — cluster accounts into N groups using a configurable metric (revenue, account count, workload hours)
- **Zone** — assign geographic parts to the nearest partition centroid using expanding spatial contours
- **Realign** — iteratively swap border parts between adjacent territories to minimize metric deviation while preserving contiguity

Output: a territory solution `FeatureCollection`
Note: pipeline is informed by the existing EZT Designer auto-builder algorithm; PostGIS-native spatial operations will be investigated for improvements.

### 5. Realign — Modify an Existing Territory Solution
Input: an existing territory solution `FeatureCollection`; a set of realignment instructions (move these parts from territory A to territory B, or move these parts into a new territory)
Processing: reassign specified parts, re-dissolve affected territories, apply Repair to restore contiguity where needed
Output: updated territory solution `FeatureCollection`
Value: the most common ongoing operation — territory solutions drift as the business changes (new hires, lost accounts, growth in one region). Realign handles directed, explicit changes: splitting an oversized territory, absorbing a departed rep's territory, or moving a cluster of parts across a boundary.
Note: Realign handles *directed* changes (agent or user specifies what moves where). Auto Build's internal realign step handles *metric-driven* convergence during initial construction — these are distinct operations.

### 6. Analyze Territory Solution
Input: a territory solution `FeatureCollection`; an account set with business metrics; desired metrics to compute
Output: structured JSON analysis — per-territory metric totals, comparisons, balance scores
Note: this is the one tool whose output is not GeoJSON, since analysis results carry no geometry.

---

## Internal Operations

### Repair
Hole-filling and contiguity repair applied internally after Direct Build, Account Build, and Realign when part assignments produce gaps or disconnected geometry. Not exposed as a public MCP tool — it is a shared pipeline step. A future version may expose Repair as a public tool for customers who bring in territory solutions from external sources.

---

## Canonical Format — Territory Solution

Territory solutions are expressed as a GeoJSON `FeatureCollection`. Each `Feature` represents one territory (T) — the dissolved union of its assigned geographic parts (Ps).

```json
{
  "type": "FeatureCollection",
  "properties": {
    "build_date": "2026-05-04",
    "metric": "revenue",
    "part_layer": "us_zips",
    "solution_name": "East Region 2026"
  },
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "MultiPolygon", "coordinates": ["...dissolved geometry..."] },
      "properties": {
        "name": "Territory North",
        "group": "East Region",
        "metric_value": 142500.00,
        "metric_label": "revenue",
        "part_ids": ["12345", "12346", "12347"]
      }
    }
  ]
}
```

Key rules:
- Each territory feature carries **dissolved polygon geometry** — the union of all its constituent parts. The territory solution is self-contained; no separate part layer is needed to render or consume it.
- `part_ids` records which geographic parts (e.g., ZIP codes) were fused into each territory.
- GeoJSON is the only wire format for geometry-bearing inputs and outputs. All tools that produce or consume territory data speak GeoJSON.

---

## Part Layers

EZT MCP is backed by EasyTerritory's own curated geographic part layer dataset — the result of years of curation and refinement. Part layers are stored in PostgreSQL (PostGIS) and hosted by EasyTerritory.

Available layers in v1: US ZIP codes, US counties, US states, Canadian FSAs. Additional layers are an operational concern.

Callers reference part layers by name (e.g., `"us_zips"`). EZT MCP resolves geometries internally.

---

## Infrastructure Model

EasyTerritory hosts all infrastructure. Customers are not responsible for deployment.

- **EZT MCP server** — stateless; hosted by EasyTerritory
- **PostgreSQL (PostGIS)** — hosted by EasyTerritory in Azure; contains part layers and geocode cache only; no customer-specific territory data
- **Customer's agent** — holds all customer-specific data: territory solutions, account lists, alignment files
- **Auth** — API key per customer; Bearer token on every request

EZT MCP is stateless per-request beyond the shared part layer and geocode cache. Customer territory solutions are returned to the agent and are the agent's responsibility to store.

---

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

- Not a SaaS product with a UI — it is an MCP server for agent access
- Not a replacement for EZT Designer — it produces and modifies territory solutions; the Designer remains the visual editing surface
- Not multi-tenant in the database sense — Postgres holds only shared reference data; no per-customer rows
- No real-time map rendering — output is data, not maps
- No EZT Designer v2 export format in v1 — format TBD; will be added when spec exists
- No in-place mutation of existing Designer projects in v1 — EZT MCP builds new solutions

---

## Lifecycle

This project follows a waterfall lifecycle:

- Vision ← you are here
- Constitution — non-negotiables: architecture, stack, security, coding conventions, deployment model
- Functional Spec — behavior definition: tools, resources, prompts, canonical format schema, error handling
- Technical Spec — architecture and design: module breakdown, data flow, retrieval pipeline, API surface
- Implementation — execution
- Verification — QA, test vectors, eval sets

EZT MCP forks from `brianhearn/ep-mcp`. The EP MCP retrieval engine is retained as the knowledge layer backbone. EZT-specific tools (build, geocode, analyze) are added on top.

---

*This document is the product intent record for EZT MCP. It will not be updated as implementation proceeds — deviations are tracked in CHANGELOG.md. The Constitution, Functional Spec, and Technical Spec are the authoritative downstream artifacts.*
