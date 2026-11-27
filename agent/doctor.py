import json
import uuid

from agent.storage import Store


def analyze_session(store: Store, session_id: str) -> dict:
    events = store.events(session_id)
    stats = store.session_stats(session_id)
    run_usage = []
    for run in store.session_runs(session_id):
        usage = run.get("usage", {})
        complete = usage.get("complete") is True
        run_usage.append(
            {
                "run_id": run["id"],
                "input_tokens": usage.get("input_tokens") if complete else None,
                "output_tokens": usage.get("output_tokens") if complete else None,
                "usage_complete": complete,
            }
        )
    findings = []
    by_run: dict[str, list[dict]] = {}
    for event in events:
        by_run.setdefault(event["run_id"], []).append(event)
    for run_id, run_events in by_run.items():
        failures: dict[str, list[dict]] = {}
        for event in run_events:
            if event["type"] == "tool_result" and not event["data"].get("ok"):
                name = str(event["data"].get("name", "unknown"))
                failures.setdefault(name, []).append(event)
        for name, failed in failures.items():
            if len(failed) >= 2:
                findings.append(
                    finding(
                        "repeated_tool_error",
                        run_id,
                        [event["id"] for event in failed],
                        {"tool": name, "failures": len(failed)},
                        f"Tool {name} failed {len(failed)} times in one run.",
                        "Inspect the first error before repeating the same call.",
                    )
                )
        completed = [
            event
            for event in run_events
            if event["type"] == "run_finished"
            and event["data"].get("status") == "completed"
        ]
        verified = [event for event in run_events if event["type"] == "task_completed"]
        if completed and not verified:
            findings.append(
                finding(
                    "completed_without_verification",
                    run_id,
                    [completed[-1]["id"]],
                    {"completed_events": len(completed), "verified_tasks": 0},
                    "The run completed without a recorded verified task.",
                    "Require runtime evidence before storing a completed result.",
                )
            )
        for index, event in enumerate(run_events):
            if event["type"] != "skill_loaded":
                continue
            later_actions = [
                item
                for item in run_events[index + 1 :]
                if item["type"] in {"tool_call", "mcp_call", "task_completed"}
                and item["data"].get("name") != "load_skill"
            ]
            if not later_actions:
                findings.append(
                    finding(
                        "unused_loaded_skill",
                        run_id,
                        [event["id"]],
                        {"skill": event["data"].get("name"), "later_actions": 0},
                        "A skill was loaded but no related action followed.",
                        "Tighten the skill description or load it only when needed.",
                    )
                )
    return {
        "session_id": session_id,
        "events_analyzed": len(events),
        "stats": stats,
        "run_usage": run_usage,
        "findings": findings,
        "limitations": [] if events else ["No events are available for this session."],
    }


def finding(
    kind: str,
    run_id: str,
    event_ids: list[str],
    counters: dict,
    interpretation: str,
    suggestion: str,
) -> dict:
    return {
        "id": uuid.uuid4().hex,
        "type": kind,
        "run_id": run_id,
        "event_ids": event_ids,
        "counters": counters,
        "interpretation": interpretation,
        "suggestion": suggestion,
    }


def format_report(report: dict) -> str:
    stats = report["stats"]
    usage = (
        f"input={stats['input_tokens']}; output={stats['output_tokens']}"
        if stats["usage_complete"]
        else "unknown or incomplete"
    )
    lines = [
        f"Doctor: session {report['session_id']}",
        f"Events analyzed: {report['events_analyzed']}",
        f"Runs: {stats['runs']}; tokens: {usage}",
        f"Skills: {stats['skills'] or 'none'}",
        f"Tools: {stats['tools'] or 'none'}",
        f"MCP calls: {stats['mcp'] or 'none'}",
    ]
    for run in report["run_usage"]:
        detail = (
            f"input={run['input_tokens']}; output={run['output_tokens']}"
            if run["usage_complete"]
            else "unknown or incomplete"
        )
        lines.append(f"Run {run['run_id']}: tokens {detail}")
    if not report["findings"]:
        lines.append("Findings: none")
    for index, item in enumerate(report["findings"], 1):
        lines.extend(
            [
                f"{index}. {item['type']} — run {item['run_id']}",
                f"   Events: {', '.join(item['event_ids'])}",
                "   Counters: " + json.dumps(item["counters"], ensure_ascii=False),
                f"   Meaning: {item['interpretation']}",
                f"   Suggestion: {item['suggestion']}",
            ]
        )
    for limitation in report["limitations"]:
        lines.append(f"Limitation: {limitation}")
    return "\n".join(lines)
