# schemas/examples/ — Contract Test Vectors

These files are schema-valid example payloads for the EZT MCP external tool contracts.

Each `*.request.json` validates against the tool schema's `#/$defs/request` definition. Each `*.response.json` validates against `#/$defs/response`.

## Coverage

| Tool / mode | Request | Response |
|---|---|---|
| `direct_build` flat TAL | `direct_build.flat.request.json` | `direct_build.flat.response.json` |
| `direct_build` hierarchical TAL | `direct_build.hierarchical.request.json` | `direct_build.hierarchical.response.json` |
| `auto_build` Mode A — fixed territory count | `auto_build.mode_a.request.json` | `auto_build.mode_a.response.json` |
| `auto_build` Mode B — fixed workload target | `auto_build.mode_b.request.json` | `auto_build.mode_b.response.json` |
| `auto_build` Scoped Split | `auto_build.scoped_split.request.json` | `auto_build.scoped_split.response.json` |
| `realign` directed part moves | `realign.request.json` | `realign.response.json` |
| `analyze` scoped + compare + hypothetical | `analyze.request.json` | `analyze.response.json` |
| `map_session_create` select mode | `map_session_create.request.json` | `map_session_create.response.json` |

`manifest.json` maps every example to the schema and definition it should validate against.
