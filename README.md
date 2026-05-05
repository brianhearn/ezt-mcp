# EZT MCP — Agentic Territory Intelligence

> Server-side territory operations for AI agents, backed by EasyTerritory domain expertise.

**Status:** Pre-implementation — Vision and Constitution complete. See [VISION.md](VISION.md) for product intent.

---

## What It Does

EZT MCP is an MCP server that gives AI agents the ability to build, balance, and analyze territory solutions — the same operations that previously required a trained user inside EZT Designer.

**MVP tools:**
- **Geocode Address** — address strings → GeoJSON point features, with shared PostgreSQL cache
- **Direct Build** — alignment file (ZIP code → territory name mapping) + part layer → territory solution
- **Account Build** — accounts with a grouping attribute (e.g., sales manager) → inferred territory solution with hole-filling and contiguity repair
- **Auto Build** — account data + metric + target territory count → balanced territory solution
- **Realign** — move parts between territories (or into a new territory) in an existing solution
- **Analyze Territory Solution** — territory solution + accounts + metrics → per-territory analysis

Output is a GeoJSON territory solution — self-contained, with dissolved territory polygons and part composition metadata. Consumable by any GeoJSON-aware tool.

## Architecture

- **Hosted by EasyTerritory** — not self-hosted by customers
- **Stateless MCP server** — no customer data persisted; customer's agent owns territory solution storage
- **Shared PostgreSQL (PostGIS)** — part layers (US ZIPs, counties, states, Canadian FSAs) + geocode cache
- **ExpertPack knowledge layer** — domain expertise for territory design, EZT product knowledge, workflow guidance

## Lifecycle

| Phase | Status |
|-------|--------|
| Vision | ✅ Complete |
| Constitution | ✅ Complete |
| Functional Spec | 🔲 Not started |
| Technical Spec | 🔲 Not started |
| Implementation | 🔲 Not started |
| Verification | 🔲 Not started |

## Lineage

Forked from [`brianhearn/ep-mcp`](https://github.com/brianhearn/ep-mcp). Retains the EP MCP retrieval engine as the domain knowledge layer. Adds EZT-specific tool, resource, and prompt surfaces on top.

## License

Apache 2.0 © 2026 EasyTerritory
