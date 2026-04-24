# VISION.md — EZT MCP: Agentic Territory Intelligence

**Version:** 0.1.0
**Date:** 2026-04-24
**Status:** Draft

---

## What This Is

EZT MCP is a server-side territory intelligence service that exposes EasyTerritory's core territory operations as MCP-native capabilities. It gives AI agents the ability to perform territory work that previously required a human expert inside EZT Designer.

Agents connect to EZT MCP to build, balance, analyze, and export territory solutions — using the same domain expertise that EasyTerritory has developed over a decade, encoded as an ExpertPack knowledge layer.

---

## The Problem It Solves

Territory planning today requires a trained user, EZT Designer, and significant manual iteration. The knowledge of *what makes a good territory* — contiguity, balance, workload equity, alignment to geographic units — lives in people's heads and in a client-side application.

Three problems follow from this:

1. **Access barrier.** Territory design is expert work. Customers need trained users. Managers who know what they want cannot act on it without a specialist.
2. **Integration friction.** Customers with existing alignment files, CRM exports, or external systems cannot easily bring that data into EZT without manual transformation.
3. **No headless path.** There is no way to programmatically create or optimize territory solutions outside the Designer UI — no API, no batch pipeline, no agent interface.

EZT MCP eliminates all three.

---

## The Vision

A customer's AI agent — running OpenClaw, Claude Desktop, or any MCP-compatible host — connects to EZT MCP and can:

- **Describe a territory problem in natural language** and receive a balanced, geographically valid territory solution as structured output
- **Import an existing alignment file** (ZIP-to-territory CSV/Excel) and produce a ready-to-consume territory solution without opening Designer
- **Build from account data** — provide a list of accounts with locations and a business metric, specify a target territory count, and receive an auto-balanced solution
- **Geocode addresses** as a first-class operation, not a preprocessing step buried in another tool
- **Understand the domain** via an ExpertPack knowledge layer that encodes territory design expertise, EZT product knowledge, and guided workflows

The agent is not a thin API proxy. It is an expert system with hands.

---

## Who Uses This

**EasyTerritory customers** who run their own agents. EZT MCP is deployed by the customer or EasyTerritory as a self-hosted service — not a SaaS offering. Customers bring their MCP-compatible agent; EZT MCP provides the territory intelligence layer.

**Two primary interaction modes:**

- **Assisted** (designer present): Agent works alongside a territory designer — handling geocoding, data ingestion, balance analysis, and project creation while the human makes strategic decisions
- **Conversational** (manager-directed): A sales manager or ops lead instructs the agent in natural language. The agent translates intent into geography and produces a territory solution without requiring a territory design specialist

---

## Founding Capabilities

### 1. Direct Build — Alignment File → Territory Solution
**Input:** A ZIP-to-territory alignment file (CSV or Excel) mapping geographic parts to territory names
**Output:** A territory solution in EZT MCP canonical format (GeoJSON profile, defined in Functional Spec)
**Value:** Covers the most common onboarding scenario — customers migrating from spreadsheets, other tools, or manual systems

### 2. Auto Build — Accounts + Metrics → Territory Solution
**Input:** Account list (locations + business metric), geographic part layer (ZIPs, counties, etc.), target territory count, optional constraints
**Processing:** Three-stage pipeline:
  - **Partition** — cluster accounts into N groups using a configurable metric (revenue, account count, workload hours)
  - **Zone** — assign geographic parts to the nearest partition centroid using expanding spatial contours
  - **Realign** — iteratively swap border parts between adjacent territories to minimize metric deviation while preserving contiguity
**Output:** Balanced territory solution in canonical format
**Note:** This pipeline is informed by the existing EZT Designer auto-builder algorithm. We will port and improve it, investigating better approaches (e.g., PostGIS-native spatial operations, improved clustering strategies) while using the current algorithm as a validated baseline.

### 3. Geocoder — Address → Coordinates
**Input:** One or more address strings
**Output:** Lat/lon coordinates via Azure Maps
**Value:** First-class operation; required by Auto Build when account locations are provided as addresses rather than coordinates

---

## The Knowledge Layer

EZT MCP is backed by an ExpertPack — a structured knowledge file set that encodes:

- Territory design principles (contiguity, balance, workload equity, geographic unit selection)
- EZT product knowledge (Designer concepts, project structure, terminology)
- Workflow guidance (how to approach common territory problems, what questions to ask, what constraints matter)
- EZT MCP tooling knowledge (when to use which tool, how to chain operations, how to interpret results)

This ExpertPack will be a new or significantly augmented pack — not a direct copy of the existing `ezt-designer` pack. It will emphasize operational knowledge (how to do things) alongside product knowledge (what things are), with less focus on internal Designer implementation details and more focus on territory planning patterns that customers care about.

The retrieval layer (EP MCP) provides the same hybrid search pipeline (BM25 + vector, intent-aware routing, `requires:` expansion) already proven at 97.6% retrieval accuracy in production.

---

## The Canonical Format

Territory solutions produced by EZT MCP are expressed as a **GeoJSON profile** — standard GeoJSON extended with required EZT MCP properties. Each territory is a `Feature` with:

- Dissolved polygon geometry (the union of its constituent geographic parts)
- Required properties: `name`, `group`, `metric_value`, `metric_label`, `part_ids` (array of constituent part identifiers)
- Optional properties: `locked`, `symbology`, `source_layer`

A complete territory solution is a `FeatureCollection` of territory features plus a solution-level `properties` block (metadata: build date, metric used, part layer reference, etc.).

This format is:
- Consumable directly by any GeoJSON-aware tool
- Rich enough to reconstruct the full territory assignment
- The target import format for EZT Designer v1 (via new import capability) and v2 (native)

Formal schema is defined in the Functional Spec.

---

## What This Is Not (Yet)

- **Not a SaaS product.** Self-hosted by customer or EasyTerritory.
- **Not a replacement for EZT Designer.** It produces territory solutions; the Designer remains the visual editing surface.
- **No real-time map rendering.** Output is data, not maps.
- **No EZT Designer v2 export format defined yet.** Benton's v2 format is TBD; export will be added when the spec exists.
- **No realignment of existing Designer projects** in v1. The MCP builds new solutions; in-place mutation of live Designer projects is a future capability.
- **No multi-tenant auth** in v1. Single-tenant deployment; multi-tenancy is a future concern.

---

## Lifecycle

This project follows a waterfall lifecycle:

1. **Vision** ← *you are here*
2. **Constitution** — non-negotiables: architecture, stack, security, coding conventions, testing, database rules, deployment model, forbidden libraries
3. **Functional Spec** — behavior definition: tools, resources, prompts, canonical format schema, error handling
4. **Technical Spec** — architecture and design: module breakdown, data flow, retrieval pipeline, API surface
5. **Implementation** — execution
6. **Verification** — QA, test vectors, eval sets

---

## Relationship to EP MCP

EZT MCP forks from `brianhearn/ep-mcp`. The EP MCP retrieval engine is retained and serves as the knowledge layer backbone. The EZT-specific tool layer (build, geocode, export) is added on top. EP-specific retrieval tools (`ep_search`, `ep_list_topics`, `ep_graph_traverse`) are either repurposed or supplemented — the ExpertPack backing EZT MCP is queried using the same proven pipeline.

The fork preserves: transport layer (Starlette/Uvicorn), auth scaffolding (API key), config.yaml pattern, CLI entry point, SQLite indexing, and the full retrieval pipeline.

The fork replaces: the pack-as-knowledge-source assumption is extended — the ExpertPack remains the domain knowledge source, but EZT MCP also has live data sources (the EZT REST API, Azure Maps, and the customer's account/geographic data).

---

*This document is the product intent record for EZT MCP. It will not be updated as implementation proceeds — deviations are tracked in CHANGELOG.md. The Constitution, Functional Spec, and Technical Spec are the authoritative downstream artifacts.*
