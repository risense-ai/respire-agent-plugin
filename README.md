# respire-agent-plugin

A **generic, vendor-neutral plugin** implementing the open
[Agent Plugins 1.0.0](https://agent-plugins.org/) standard. It packages the
respire (`rsrs`) encrypted local memory engine so that *any* compatible agent
client can load it without repackaging:

- **Skill** — `skills/respire-memory/SKILL.md`: recall-before-answering and
  store-when-wrapping-up workflow for the `rsrs` CLI.
- **MCP server** — `mcp.json` + `mcp/server.py`: a dependency-free stdio MCP
  server exposing `respire_recall`, `respire_remember`, `respire_status`.
- **Client extension namespace** — `com.risense.respire/` + the matching
  `extensions` entry in `plugin.json` (ignored by clients that don't
  implement it, per spec §8).

## Layout

```
respire-agent-plugin/
├── plugin.json                 # required manifest (closed schema, 1.0.0)
├── skills/
│   └── respire-memory/
│       └── SKILL.md            # Agent Skill (frontmatter + body)
├── mcp.json                    # stdio MCP server declaration
├── mcp/
│   └── server.py               # stdlib-only MCP stdio server
├── com.risense.respire/        # client-specific namespace (no portable rules)
├── scripts/
│   └── validate_plugin.py      # offline conformance validator
├── LICENSE
└── README.md
```

## Install

Distribution is intentionally out of scope of the standard (each client owns
it). In general, drop this directory anywhere and point your client at it —
the package is self-contained, uses only `./`-relative paths, and contains no
symlinks.

## Requirements

- `rsrs` (respire CLI) on `PATH` for the memory tools to function; without it
  the MCP server still starts and reports a clear error on tool calls.
- `python3` on `PATH` for the stdio server (declared as a bare executable
  token, per spec).

## Validate

```bash
python3 scripts/validate_plugin.py .
```

Checks the normative portability rules: closed manifest schema, name pattern,
skill discovery layout (no recursive discovery), `mcp.json` schema-version
match, per-transport rules, `PLUGIN_ROOT`/`PLUGIN_DATA` bans, and
loopback-HTTPS enforcement.

## Smoke-test the MCP server

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python3 mcp/server.py
```

## Safety

The memory store is encrypted locally, but never write secrets (passwords,
IDs, cards, keys) into memory bodies or query terms — record only *where* they
are stored. See `skills/respire-memory/SKILL.md`.

## License

MIT
