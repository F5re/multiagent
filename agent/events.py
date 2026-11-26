import json


def format_event(event: dict) -> str:
    kind = event["type"]
    data = event["data"]
    if kind == "run_started":
        return f"[agent] Run started: {event['run_id']}"
    if kind == "run_finished":
        return f"[agent] Run finished: {data.get('status', 'unknown')}"
    if kind == "model_usage":
        incoming = data.get("input_tokens", "unknown")
        outgoing = data.get("output_tokens", "unknown")
        return f"[usage] input={incoming}; output={outgoing}"
    if kind == "tool_call":
        return f"[tool] {data.get('name', 'unknown')}: requested"
    if kind == "tool_result":
        status = "success" if data.get("ok") else "error"
        return f"[tool] {data.get('name', 'unknown')}: {status}"
    if kind == "approval":
        decision = "approved" if data.get("approved") else "rejected"
        return f"[approval] {data.get('name', 'action')}: {decision}"
    if kind == "error":
        return f"[error] {data.get('message', 'unknown error')}"
    if kind == "skill_loaded":
        return f"[skill] Loaded: {data.get('name', 'unknown')}"
    if kind == "mcp_call":
        return f"[mcp] {data.get('server')}/{data.get('name')}: requested"
    return f"[{kind}] {json.dumps(data, ensure_ascii=False)}"


def format_stats(stats: dict) -> str:
    usage = (
        f"input={stats['input_tokens']}; output={stats['output_tokens']}"
        if stats["usage_complete"]
        else "unknown or incomplete"
    )
    lines = [
        f"Session: {stats['session_id']}",
        f"Runs: {stats['runs']}; events: {stats['events']}",
        f"Tokens: {usage}",
        f"Tools ({stats['unique_tools']} unique): {stats['tools'] or 'none'}",
        f"Skills ({stats['unique_skills']} unique): {stats['skills'] or 'none'}",
        f"MCP calls: {stats['mcp'] or 'none'}",
    ]
    return "\n".join(lines)
