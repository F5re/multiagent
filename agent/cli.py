import argparse
import json
import sys
from pathlib import Path

from agent.doctor import analyze_session, format_report
from agent.engine import Agent, AgentError
from agent.evals import EvalError, EvalRunner
from agent.events import format_event, format_stats
from agent.model import ChatModel, ModelError
from agent.policy import PolicyError
from agent.storage import StateConflict, Store


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
    run.add_argument("--session")
    chat = commands.add_parser("chat")
    chat.add_argument("--mode", choices=("safe", "auto"), default="auto")
    chat.add_argument("--session")
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
    commands.add_parser("stats").add_argument("session_id")
    events = commands.add_parser("events")
    events.add_argument("session_id")
    events.add_argument("--jsonl", type=Path)
    doctor = commands.add_parser("doctor")
    doctor.add_argument("session_id")
    doctor.add_argument("--json", action="store_true")
    evaluation = commands.add_parser("eval")
    evaluation_commands = evaluation.add_subparsers(dest="eval_command", required=True)
    evaluation_run = evaluation_commands.add_parser("run")
    evaluation_run.add_argument("--trials", type=int, default=3)
    evaluation_run.add_argument(
        "--cases", type=Path, default=root / "evals" / "cases.json"
    )
    evaluation_run.add_argument(
        "--output", type=Path, default=root / "results" / "baseline"
    )
    evaluation_commands.add_parser("summary").add_argument(
        "--output", type=Path, default=root / "results" / "baseline"
    )
    return result


def main(arguments: list[str] | None = None) -> int:
    arguments_object = parser().parse_args(arguments)
    try:
        if arguments_object.command == "eval":
            runner = EvalRunner(
                Path(__file__).resolve().parent.parent,
                getattr(
                    arguments_object,
                    "cases",
                    Path(__file__).resolve().parent.parent / "evals" / "cases.json",
                ),
                arguments_object.output,
            )
            if arguments_object.eval_command == "run":
                results = runner.run(arguments_object.trials)
                print(f"Eval trials saved: {len(results)}")
            else:
                results = runner.read_results()
                runner.write_summary(results)
                print(f"Summary written: {arguments_object.output / 'summary.md'}")
            return 0
        if arguments_object.command in {"stats", "events", "doctor"}:
            store = Store(arguments_object.state)
            if arguments_object.command == "stats":
                print(format_stats(store.session_stats(arguments_object.session_id)))
            elif arguments_object.command == "doctor":
                report = analyze_session(store, arguments_object.session_id)
                if arguments_object.json:
                    print(json.dumps(report, ensure_ascii=False, indent=2))
                else:
                    print(format_report(report))
            elif arguments_object.jsonl:
                store.export_events(arguments_object.session_id, arguments_object.jsonl)
                print(f"Events exported: {arguments_object.jsonl}")
            else:
                for event in store.events(arguments_object.session_id):
                    print(format_event(event))
            return 0
        agent = Agent(
            arguments_object.workspace,
            arguments_object.policy,
            arguments_object.state,
            ChatModel(),
        )
        if arguments_object.command == "chat":
            return chat_loop(agent, arguments_object.mode, arguments_object.session)
        if arguments_object.command == "run":
            state = agent.start(
                arguments_object.request,
                arguments_object.mode,
                arguments_object.session,
            )
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
        EvalError,
    ) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


def show(state: dict) -> None:
    print(f"Run: {state['id']}")
    if state.get("session_id"):
        print(f"Session: {state['session_id']}")
    print(f"Status: {state['phase']}")
    if state["phase"] == "waiting_plan":
        print(f"Plan: {state['plan']['goal']}")
        for index, task in enumerate(state["plan"]["steps"], 1):
            dependencies = ", ".join(task["depends_on"]) or "none"
            print(f"  {index}. {task['id']}: {task['description']}")
            print(f"     tools: {', '.join(task['tools'])}; depends on: {dependencies}")
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


def chat_loop(agent: Agent, mode: str, session_id: str | None) -> int:
    session_id = agent.store.create_session(session_id)
    print(f"Session: {session_id}")
    print("Commands: /stats, /events, /exit")
    while True:
        try:
            request = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSession closed.")
            return 0
        if not request:
            continue
        if request == "/exit":
            print("Session closed.")
            return 0
        if request == "/stats":
            print(format_stats(agent.store.session_stats(session_id)))
            continue
        if request == "/events":
            for event in agent.store.events(session_id):
                print(format_event(event))
            continue
        state = agent.start(request, mode, session_id)
        while state["phase"] in {"waiting_plan", "waiting_action", "uncertain"}:
            show(state)
            if state["phase"] == "waiting_plan":
                answer = input("Approve plan? [y/N] ").strip().lower()
                state = agent.approve_plan(state["id"], answer in {"y", "yes"})
            elif state["phase"] == "waiting_action":
                answer = input("Approve action? [y/N] ").strip().lower()
                state = agent.decide_action(state["id"], answer in {"y", "yes"})
            else:
                decision = input("Resolve [retry/fail/abort]: ").strip().lower()
                if decision not in {"retry", "fail", "abort"}:
                    print("Choose retry, fail, or abort.")
                    continue
                state = agent.resolve(state["id"], decision)
        show(state)


def entrypoint() -> None:
    raise SystemExit(main())
