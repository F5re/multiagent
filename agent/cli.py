import argparse
import json
import sys
from pathlib import Path

from agent.engine import Agent, AgentError
from agent.model import ChatModel, ModelError
from agent.policy import PolicyError
from agent.storage import StateConflict


def parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parent.parent
    result = argparse.ArgumentParser(prog="coding-agent")
    result.add_argument("--workspace", type=Path, default=root / "workspace")
    result.add_argument("--policy", type=Path, default=root / "config" / "policy.json")
    result.add_argument(
        "--state", type=Path, default=root / ".agent_state" / "runs.sqlite3"
    )
    commands = result.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("request")
    run.add_argument("--mode", choices=("safe", "auto"), default="auto")
    for name in (
        "resume",
        "status",
        "approve-plan",
        "reject-plan",
        "approve",
        "reject",
    ):
        commands.add_parser(name).add_argument("run_id")
    recovery = commands.add_parser("resolve")
    recovery.add_argument("run_id")
    recovery.add_argument("decision", choices=("retry", "fail", "abort"))
    return result


def main(arguments: list[str] | None = None) -> int:
    arguments_object = parser().parse_args(arguments)
    try:
        agent = Agent(
            arguments_object.workspace,
            arguments_object.policy,
            arguments_object.state,
            ChatModel(),
        )
        if arguments_object.command == "run":
            state = agent.start(arguments_object.request, arguments_object.mode)
        elif arguments_object.command == "resume":
            state = agent.drive(arguments_object.run_id)
        elif arguments_object.command == "status":
            state = agent.store.load(arguments_object.run_id)
        elif arguments_object.command in {"approve-plan", "reject-plan"}:
            state = agent.approve_plan(
                arguments_object.run_id,
                arguments_object.command == "approve-plan",
            )
        elif arguments_object.command in {"approve", "reject"}:
            state = agent.decide_action(
                arguments_object.run_id,
                arguments_object.command == "approve",
            )
        else:
            state = agent.resolve(arguments_object.run_id, arguments_object.decision)
        show(state)
        return 0
    except (
        AgentError,
        ModelError,
        PolicyError,
        StateConflict,
        KeyError,
        ValueError,
    ) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


def show(state: dict) -> None:
    print(f"Run: {state['id']}")
    print(f"Status: {state['phase']}")
    if state["phase"] == "waiting_plan":
        print("Plan:")
        print(json.dumps(state["plan"], ensure_ascii=False, indent=2))
    if state["phase"] == "waiting_action":
        call = state["calls"][state["queue"][0]]
        print(f"Approval required: {call['name']}")
        print("Arguments: " + json.dumps(call["arguments"], ensure_ascii=False))
    if state["phase"] == "uncertain":
        call = state["calls"][state["queue"][0]]
        print(f"Unknown result: {call['name']} ({call['id']})")
    if state["tasks"]:
        print("Tasks:")
        for task in state["tasks"]:
            print(f"  {task['id']}: {task['status']}")
    if state["error"]:
        print("Error: " + state["error"])
    if state["answer"]:
        print("Result:")
        print(state["answer"])


def entrypoint() -> None:
    raise SystemExit(main())
