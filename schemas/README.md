# schemas/ — EZT MCP External Contracts

**Status:** Draft schemas for the Functional Spec v0.1.x surface.

These JSON Schemas define externally visible MCP request/response structures. They complement [FUNCTIONAL_SPEC.md](../FUNCTIONAL_SPEC.md): schemas own structure; the Functional Spec owns behavior.

## Draft schema set

| Schema | Purpose |
|---|---|
| `common.schema.json` | Shared success/error envelope, warnings, structured errors, and common scalar definitions. |
| `ts-reference.schema.json` | TS identity plus `ts` / `ts_handle` reference conventions. |
| `direct_build.schema.json` | `direct_build` request and response payloads. |
| `auto_build.schema.json` | `auto_build` request and response payloads, including Mode A, Mode B, and Scoped Split. |
| `realign.schema.json` | `realign` request and response payloads, including directed part-move operations and map session refresh. |
| `analyze.schema.json` | `analyze` request and response payloads, including TAL analysis, scoped aggregates, cross-TAL comparison, and hypothetical impact. |
| `map_session_create.schema.json` | `map_session_create` request and response payloads, including session mode, presentation context, and resource URIs. |

## Notes

- Draft target is JSON Schema 2020-12.
- Schemas are intentionally behavioral-contract oriented, not implementation/database schemas.
- Full TS GeoJSON validation is represented as a permissive object placeholder for now; a dedicated TS schema should be added once the TS property conventions stabilize.
