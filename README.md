# EZT MCP — Agentic Territory Intelligence

> Server-side territory operations for AI agents, backed by EasyTerritory domain expertise.

**Status:** Pre-implementation — Vision phase complete. See [VISION.md](VISION.md) for product intent.

---

## What It Does

EZT MCP is an MCP server that gives AI agents the ability to build, balance, and export territory solutions — the same operations that previously required a trained user inside EZT Designer.

**Founding capabilities:**
- **Direct Build** — alignment file (ZIP → territory name) → territory solution
- **Auto Build** — account data + metric + target count → balanced territory solution
- **Geocoder** — address strings → coordinates via Azure Maps

Output is a GeoJSON-profiled territory solution consumable by any MCP-compatible agent and importable into EZT Designer.

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
