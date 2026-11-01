# com.risense.respire — client extension namespace

This directory holds **client-specific** configuration for the respire memory
plugin. Per the Agent Plugins 1.0.0 specification (§8), contents under a
reverse-DOMAIN namespace have **no portable semantics** — each client decides
how (and whether) to read them.

Manifest data for this namespace lives in `plugin.json` under
`extensions["com.risense.respire"]`:

```json
{
  "displayName": "Respire Memory",
  "engine": "rsrs",
  "minCliVersion": "1.0.0",
  "docs": "./com.risense.respire/README.md"
}
```

| Field         | Meaning                                                        |
| ------------- | -------------------------------------------------------------- |
| `displayName` | Human-readable name a client may show in its UI                |
| `engine`      | Underlying engine binary (`rsrs` CLI)                          |
| `minCliVersion` | Minimum `rsrs` CLI version the plugin expects                |
| `docs`        | Relative pointer to this namespace documentation               |

Clients that do not implement `com.risense.respire` MUST ignore both the
manifest entry and this directory without validating their contents.
