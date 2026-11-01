#!/usr/bin/env python3
"""Offline validator for an Agent Plugins 1.0.0 package.

Checks the normative rules that matter for portability:
  - plugin.json: canonical $schema, closed top-level field set, name pattern,
    typed optional metadata, extensions values are objects
  - skills/: immediate children with SKILL.md regular files, no symlink escape
  - mcp.json: canonical $schema matching plugin.json, closed top-level fields,
    per-transport rules (command token, url form, cwd forms, env bans)
  - top-level extension directories referenced by manifest namespaces

Exit 0 when the package is conformant (warnings allowed), 1 otherwise.
"""

import json
import re
import sys
from pathlib import Path

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"

PLUGIN_FIELDS = {
    "$schema", "name", "version", "description", "author",
    "homepage", "repository", "license", "keywords", "extensions",
}
AUTHOR_FIELDS = {"name", "email", "url"}

NAME_RE = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
CWD_RE = re.compile(r"^(?:\./|\$\{PLUGIN_ROOT\}(?:/|$)|\$\{PLUGIN_DATA\}(?:/|$))")

errors = []
warnings = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        err(f"{path.name}: missing")
    except json.JSONDecodeError as exc:
        err(f"{path.name}: invalid JSON ({exc})")
    return None


def check_manifest(root):
    data = load_json(root / "plugin.json")
    if data is None:
        return None

    if data.get("$schema") != PLUGIN_SCHEMA:
        err(f"plugin.json: $schema must be {PLUGIN_SCHEMA!r}")

    for field in data:
        if field not in PLUGIN_FIELDS:
            err(f"plugin.json: unknown top-level field {field!r} (closed schema)")

    name = data.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name) or len(name) > 64:
        err(f"plugin.json: invalid name {name!r}")

    for field in ("version", "description", "homepage", "repository", "license"):
        if field in data and not isinstance(data[field], str):
            err(f"plugin.json: {field} must be a string")

    if "author" in data:
        author = data["author"]
        if not isinstance(author, dict):
            err("plugin.json: author must be an object")
        else:
            for key in author:
                if key not in AUTHOR_FIELDS:
                    err(f"plugin.json: unknown author field {key!r}")
            for key, value in author.items():
                if not isinstance(value, str):
                    err(f"plugin.json: author.{key} must be a string")

    if "keywords" in data and (
        not isinstance(data["keywords"], list)
        or not all(isinstance(k, str) for k in data["keywords"])
    ):
        err("plugin.json: keywords must be an array of strings")

    extensions = data.get("extensions", {})
    if not isinstance(extensions, dict):
        err("plugin.json: extensions must be an object (non-fatal per spec, "
            "but treated as error here for author discipline)")
        extensions = {}
    for ns, value in extensions.items():
        if not isinstance(value, dict):
            err(f"plugin.json: extensions[{ns!r}] must be an object")
        if not re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", ns):
            err(f"plugin.json: extension namespace {ns!r} is not reverse-domain")
        if not (root / ns).is_dir():
            warn(f"extension namespace {ns!r} has no matching top-level "
                 f"directory {ns}/")
    return data


def check_skills(root):
    skills_dir = root / "skills"
    if not skills_dir.exists():
        warn("skills/ not present (skills are optional)")
        return
    if not skills_dir.is_dir():
        err("skills/ must be a directory")
        return
    count = 0
    for child in sorted(skills_dir.iterdir()):
        if child.is_symlink():
            err(f"skills/{child.name}: symlinks must not escape the package")
            continue
        if not child.is_dir():
            warn(f"skills/{child.name}: ignored (not a skill directory)")
            continue
        skill_md = child / "SKILL.md"
        if skill_md.is_symlink():
            err(f"skills/{child.name}/SKILL.md: symlinks not allowed")
        elif not skill_md.is_file():
            err(f"skills/{child.name}: missing SKILL.md")
        else:
            body = skill_md.read_text(encoding="utf-8")
            if not body.startswith("---"):
                err(f"skills/{child.name}/SKILL.md: missing YAML frontmatter")
            count += 1
        # spec: no recursive discovery
        for nested in child.rglob("SKILL.md"):
            if nested.parent != child:
                warn(f"skills/{child.name}: nested SKILL.md at "
                     f"{nested.relative_to(root)} is NOT discovered by clients")
    if count == 0:
        warn("skills/: no valid skills found")


def check_mcp(root, manifest):
    path = root / "mcp.json"
    if not path.exists():
        return
    data = load_json(path)
    if data is None:
        return

    if data.get("$schema") != MCP_SCHEMA:
        err(f"mcp.json: $schema must be {MCP_SCHEMA!r}")
    if manifest and isinstance(manifest.get("version"), str):
        # version match rule compares schema versions, not plugin versions;
        # both $schema consts pin 1.0.0, checked above. Nothing else to do.
        pass
    for field in data:
        if field not in ("$schema", "mcpServers"):
            err(f"mcp.json: unknown top-level field {field!r} (closed schema)")

    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        err("mcp.json: mcpServers must be an object")
        return
    if not servers:
        warn("mcp.json: mcpServers is empty")

    types_seen = set()
    for sname, server in servers.items():
        if not isinstance(server, dict):
            err(f"mcp.json: server {sname!r} must be an object")
            continue
        stype = server.get("type")
        types_seen.add(stype)
        for field in server:
            if field not in ("type", "command", "args", "env", "cwd",
                             "url", "headers"):
                err(f"mcp.json: server {sname!r}: unknown field {field!r}")
        if stype == "stdio":
            cmd = server.get("command")
            if not isinstance(cmd, str) or not cmd:
                err(f"mcp.json: server {sname!r}: command required")
            elif "${" in cmd:
                err(f"mcp.json: server {sname!r}: command must not contain "
                    "placeholders")
            elif not re.match(r"^(?:[A-Za-z0-9._+-]+|\./.+)$", cmd):
                err(f"mcp.json: server {sname!r}: command must be a bare "
                    "executable token or ./-relative")
            if "args" in server and (
                not isinstance(server["args"], list)
                or not all(isinstance(a, str) for a in server["args"])
            ):
                err(f"mcp.json: server {sname!r}: args must be string array")
            env = server.get("env", {})
            if not isinstance(env, dict):
                err(f"mcp.json: server {sname!r}: env must be an object")
            else:
                for key in env:
                    if key in ("PLUGIN_ROOT", "PLUGIN_DATA"):
                        err(f"mcp.json: server {sname!r}: env must not define "
                            "PLUGIN_ROOT/PLUGIN_DATA")
                    if not isinstance(env[key], str):
                        err(f"mcp.json: server {sname!r}: env values must be "
                            "strings")
            if "cwd" in server and (
                not isinstance(server["cwd"], str)
                or not CWD_RE.match(server["cwd"])
            ):
                err(f"mcp.json: server {sname!r}: cwd must be ./-, "
                    "${PLUGIN_ROOT}- or ${PLUGIN_DATA}-rooted")
        elif stype in ("streamable-http", "sse"):
            url = server.get("url")
            if not isinstance(url, str) or not url:
                err(f"mcp.json: server {sname!r}: url required")
            elif not re.match(r"^https?://", url):
                err(f"mcp.json: server {sname!r}: url must be absolute")
            else:
                rest = url.split("://", 1)[1]
                if "@" in rest.split("/", 1)[0]:
                    err(f"mcp.json: server {sname!r}: url must not contain "
                        "userinfo")
                if "#" in url:
                    err(f"mcp.json: server {sname!r}: url must not contain "
                        "a fragment")
                host = rest.split("/", 1)[0].split(":", 1)[0]
                loopback = host in ("localhost", "127.0.0.1", "::1")
                if stype in ("streamable-http", "sse") and not loopback \
                        and url.startswith("http://"):
                    err(f"mcp.json: server {sname!r}: non-loopback HTTP must "
                        "be HTTPS")
        else:
            err(f"mcp.json: server {sname!r}: unsupported type {stype!r}")

    if not ({"stdio", "streamable-http"} & types_seen):
        err("mcp.json: clients MUST support stdio or streamable-http; "
            "package provides neither")


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    root = root.resolve()
    manifest = check_manifest(root)
    check_skills(root)
    check_mcp(root, manifest)

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    if errors:
        print(f"\nFAIL: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"\nPASS: conformant Agent Plugins 1.0.0 package "
          f"({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
