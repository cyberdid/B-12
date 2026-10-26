"""Minimal MCP stdio server fixture: newline-delimited JSON-RPC 2.0 (protocol 2025-06-18)."""

import json
import sys
import threading
import time
from pathlib import Path

TOOLS = [
    {
        "name": "echo",
        "description": "Echo text back",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Text to echo"}},
            "required": ["text"],
        },
    },
    {
        "name": "add",
        "description": "Add two numbers",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    },
    {
        "name": "write_note",
        "description": "Write a note file",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "text": {"type": "string"}},
            "required": ["path", "text"],
        },
    },
    {
        "name": "slow",
        "description": "Sleep",
        "inputSchema": {"type": "object", "properties": {"seconds": {"type": "number"}}},
    },
    {
        "name": "fail",
        "description": "Always errors",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "union",
        "description": "Unsupported schema",
        "inputSchema": {
            "type": "object",
            "properties": {"v": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
        },
    },
]
cancelled = set()
lock = threading.Lock()


def send(message):
    with lock:
        sys.stdout.write(json.dumps(message) + "\n")
        sys.stdout.flush()


def call(request):
    name, args = request["params"]["name"], request["params"].get("arguments", {})
    if name == "echo":
        return {"content": [{"type": "text", "text": args["text"]}], "isError": False}
    if name == "add":
        return {"content": [{"type": "text", "text": str(args["a"] + args["b"])}], "isError": False}
    if name == "write_note":
        Path(args["path"]).write_text(args["text"])
        return {"content": [{"type": "text", "text": "written"}], "isError": False}
    if name == "slow":
        end = time.monotonic() + args.get("seconds", 30)
        while time.monotonic() < end:
            if request["id"] in cancelled:
                return None
            time.sleep(0.05)
        return {"content": [{"type": "text", "text": "slept"}], "isError": False}
    if name == "fail":
        return {"content": [{"type": "text", "text": "boom"}], "isError": True}
    raise KeyError(name)


def handle(request):
    method = request.get("method")
    if method == "initialize":
        send(
            {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fixture", "version": "1"},
                },
            }
        )
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": request["id"], "result": {"tools": TOOLS}})
    elif method == "tools/call":

        def work():
            try:
                result = call(request)
            except KeyError:
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": request["id"],
                        "error": {"code": -32602, "message": "unknown tool"},
                    }
                )
                return
            if result is not None:
                send({"jsonrpc": "2.0", "id": request["id"], "result": result})

        threading.Thread(target=work, daemon=True).start()
    elif method == "notifications/cancelled":
        cancelled.add(request["params"]["requestId"])


for line in sys.stdin:
    if line.strip():
        handle(json.loads(line))
