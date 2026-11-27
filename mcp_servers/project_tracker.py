import json
import sys
import time
from pathlib import Path

DATA = Path(__file__).with_name("issues.json")

TOOLS = [
    {
        "name": "get_issue",
        "description": "Read one issue from the local project tracker.",
        "inputSchema": {
            "type": "object",
            "properties": {"issue_id": {"type": "string"}},
            "required": ["issue_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "list_issues",
        "description": "List local project issues, optionally filtered by status.",
        "inputSchema": {
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
]


def respond(identifier, result=None, error=None) -> None:
    message = {"jsonrpc": "2.0", "id": identifier}
    if error:
        message["error"] = {"code": -32000, "message": error}
    else:
        message["result"] = result
    print(json.dumps(message, ensure_ascii=False), flush=True)


def call_tool(params: dict) -> dict:
    name = params.get("name")
    arguments = params.get("arguments", {})
    if arguments.get("issue_id") == "TIMEOUT":
        time.sleep(10)
    if arguments.get("issue_id") == "ERROR":
        raise ValueError("synthetic tracker failure")
    issues = json.loads(DATA.read_text(encoding="utf-8"))
    if name == "get_issue":
        issue = next(
            (item for item in issues if item["id"] == arguments.get("issue_id")),
            None,
        )
        if issue is None:
            raise ValueError("issue not found")
        return {"content": [{"type": "text", "text": json.dumps(issue)}]}
    if name == "list_issues":
        selected = [
            item for item in issues if item["status"] == arguments.get("status")
        ]
        return {"content": [{"type": "text", "text": json.dumps(selected)}]}
    raise ValueError("unknown tool")


def main() -> None:
    for line in sys.stdin:
        message = json.loads(line)
        if "id" not in message:
            continue
        method = message.get("method")
        try:
            if method == "initialize":
                respond(
                    message["id"],
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "project-tracker", "version": "1.0.0"},
                    },
                )
            elif method == "tools/list":
                respond(message["id"], {"tools": TOOLS})
            elif method == "tools/call":
                respond(message["id"], call_tool(message.get("params", {})))
            else:
                respond(message["id"], error="method not found")
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            respond(message["id"], error=str(error))


if __name__ == "__main__":
    main()
