Version: 0.12.0
Date: 2026-05-13
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

- Geocode account data and receive a Territory Solution carrying those records as a point layer
- Import an existing alignment file and receive a ready-to-consume Territory Solution
- Build territories from scratch — from account groupings or from a target count with metric balancing
- Realign an existing Territory Solution based on user direction or map widget selections
- Analyze a Territory Solution — including comparative analysis across multiple alignment strategies
- Share Territory Solutions with management through a read-only map experience, Power BI-friendly exports, or agent-hosted narrative summaries
- Select geographic parts visually using an embedded Map Component and direct the agent to realign them
- Draw on an ExpertPack knowledge layer that encodes territory design expertise, EZT product knowledge, and guided workflows

The agent is not a thin API proxy. It is an expert system with hands. EZT MCP provides the territory intelligence — compute, knowledge, and shared reference data. It does not own customer data.

---

## Who It Serves

EasyTerritory customers who run their own agents. EZT MCP is hosted by EasyTerritory and accessed by customers as a service — not a self-hosted product. Customers bring their MCP-compatible agent host; EZT MCP provides the territory intelligence layer.

Two primary interaction modes:

- **Assisted (designer present):** Agent works alongside a territory designer — handling geocoding, data ingestion, balance analysis, and solution creation while the human makes strategic decisions.
- **Conversational (manager-directed):** A sales manager or ops lead instructs the agent in natural language. The agent translates intent into geography and produces a territory solution without requiring a specialist.

---

## Core Principles

**The Territory Solution (TS) is the primary working artifact.** It is self-contained GeoJSON — valid, portable, inspectable with any GeoJSON-aware tool. All builds, edits, and analysis operate on this artifact; tools augment an incoming TS and return an updated one.

**The customer's agent owns customer data.** EZT MCP does not persist Territory Solutions, account lists, or alignment files as a system of record. The agent passes a TS in and receives an updated TS back. EZT MCP may hold payloads transiently during request processing.

**EasyTerritory hosts all shared infrastructure.** Customers are not responsible for deployment. The stateless MCP server, the Resource Server (curated part geometries, geocode cache), and the Map Component are all operated by EasyTerritory.

**Build operations append, never replace.** A TS may carry multiple Territory Alignment Layers simultaneously. Building a new alignment adds to the TS — it does not overwrite prior work. This enables comparative analysis: run two builds with different metrics, switch between them in the Map Component, and commit to one.

**Expertise travels with the server.** The ExpertPack knowledge layer means agents get EasyTerritory's territory design expertise automatically — not as documentation to read, but as context retrieved at query time.

---

## What This Is Not

- Not a SaaS product with a full territory-management UI — it is an MCP server for agent access plus a lightweight TS viewing and sharing surface
- Not a replacement for EZT Designer — Designer remains the visual editing surface; EZT MCP is the headless compute and knowledge layer
- Not a durable customer data store — the customer's agent owns all customer artifacts
- Not a proprietary format — the TS is standard GeoJSON; no EZT-specific file type or SDK is required
- Not multi-tenant in the database sense — the Resource Server holds only shared spatial infrastructure

---

## Lifecycle

This project follows a staged documentation lifecycle:

- **Vision** ← you are here — product intent and core principles
- **Constitution** — non-negotiables: architecture, stack, security, deployment model
- **Functional Spec** — external behavior: tools, resources, error contracts, acceptance criteria
- **Technical Spec** — architecture and design: module breakdown, data flow, API surface
- **Implementation** — execution
- **Verification** — QA, test vectors, eval sets

---

*This document is the product intent record for EZT MCP. Implementation decisions, tool contracts, format specifications, infrastructure details, and design guidance belong in the downstream artifacts (Constitution, Functional Spec, Technical Spec). This document does not change as implementation proceeds — deviations are tracked in CHANGELOG.md.*
