#!/usr/bin/env python3
"""Minimal stdio MCP server exposing respire (rsrs) memory tools.

Newline-delimited JSON-RPC 2.0 over stdin/stdout, per the MCP stdio
transport. Standard library only; shells out to the `rsrs` CLI.
"""

import json
import os
import shutil
import subprocess
import sys

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "respire-memory", "version": "1.0.0"}

TOOLS = [
    {
        "name": "respire_recall",
        "description": (
            "Search the local encrypted respire memory store. Returns "
            "relevance-scored titles; use the short ids with respire_show "
            "or the rsrs CLI for full bodies."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords to recall"},
                "titles_only": {
                    "type": "boolean",
                    "description": "If true, return id+title only (--titles)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "respire_remember",
        "description": (
            "Store a durable fact into respire memory. The title must be a "
            "complete 'subject + action + result' sentence, never a topic "
            "label. Never store secrets (passwords, IDs, cards, keys)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Fact body to store"},
                "title": {
                    "type": "string",
                    "description": "Facade sentence for recall/dedup",
                },
                "importance": {
                    "type": "string",
                    "enum": ["normal", "important"],
                    "description": "Importance tier",
                },
            },
            "required": ["content", "title"],
        },
    },
    {
        "name": "respire_status",
        "description": "Show respire account/sync/engine status (rsrs status).",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def run_rsrs(args):
    """Run rsrs with args; return (exit_code, combined_output)."""
    exe = shutil.which("rsrs")
    if exe is None:
        return 127, "rsrs CLI not found on PATH. Install respire first."
    try:
        proc = subprocess.run(
            [exe] + args,
            capture_output=True,
            text=True,
            timeout=60,
            env={k: v for k, v in os.environ.items()
                 if k not in ("PLUGIN_ROOT", "PLUGIN_DATA")},
        )
    except subprocess.TimeoutExpired:
        return 124, "rsrs command timed out after 60s"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def tool_recall(args):
    query = str(args.get("query", "")).strip()
    if not query:
        return True, "query must be a non-empty string"
    argv = ["recall", query]
    if args.get("titles_only"):
        argv.append("--titles")
    code, out = run_rsrs(argv)
    if code == 127:
        return True, out
    return False, out or f"(no results, exit {code})"


def tool_remember(args):
    content = str(args.get("content", "")).strip()
    title = str(args.get("title", "")).strip()
    if not content or not title:
        return True, "content and title are required"
    argv = ["remember", content, "--title", title]
    importance = args.get("importance")
    if importance in ("normal", "important"):
        argv += ["--importance", importance]
    code, out = run_rsrs(argv)
    if code == 127:
        return True, out
    return False, out or f"(stored, exit {code})"


def tool_status(_args):
    code, out = run_rsrs(["status"])
    return code == 127, out or f"(exit {code})"


HANDLERS = {
    "respire_recall": tool_recall,
    "respire_remember": tool_remember,
    "respire_status": tool_status,
}


def handle_request(req):
    """Return a response dict, or None for notifications."""
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        handler = HANDLERS.get(name)
        if handler is None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"unknown tool: {name}"},
            }
        try:
            is_err, text = handler(params.get("arguments") or {})
        except Exception as exc:  # fail soft per MCP tool-call semantics
            is_err, text = True, f"{type(exc).__name__}: {exc}"
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": text}],
                "isError": is_err,
            },
        }

    if req_id is None:
        return None  # unknown notification: ignore
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
