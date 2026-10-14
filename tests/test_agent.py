import hashlib
import json
import shutil
from pathlib import Path

import pytest

import agent.engine as engine_module
from agent.cli import show
from agent.engine import Agent, AgentError, parse_plan
from agent.model import FakeModel, text_tool_calls
from agent.policy import Policy, PolicyError
from agent.storage import StateConflict, Store
from agent.tools import execute as real_execute

ROOT = Path(__file__).parents[1]
BROKEN = (
    "def calculate_total(prices: list[float], discount_percent: float) -> float:\n"
    "    return sum(prices) - discount_percent\n"
)
FIXED = (
    "def calculate_total(prices: list[float], discount_percent: float) -> float:\n"
    "    if not 0 <= discount_percent <= 100:\n"
    "        raise ValueError('invalid discount')\n"
    "    return sum(prices) * (1 - discount_percent / 100)\n"
)
INCOMPLETE = (
    "def calculate_total(prices: list[float], discount_percent: float) -> float:\n"
    "    if not 0 <= discount_percent <= 100:\n"
    "        raise ValueError('invalid discount')\n"
    "    return sum(prices) - discount_percent\n"
)


def call(call_id: str, name: str, **arguments: str) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def tool_reply(*calls: dict) -> dict:
    return {"content": None, "tool_calls": list(calls)}


def final(text: str) -> dict:
    return {"content": text}


def plan_reply() -> dict:
    plan = {
        "goal": "Fix order total",
        "steps": [
            {
                "id": "inspect",
                "description": "Read source and tests",
                "depends_on": [],
                "tools": ["list_files", "read_file"],
                "verification": {
                    "kind": "read_files",
                    "paths": ["order.py", "test_order.py"],
                },
            },
            {
                "id": "implement",
                "description": "Fix order.py",
                "depends_on": ["inspect"],
                "tools": ["write_file"],
                "verification": {"kind": "file_changed", "path": "order.py"},
            },
            {
                "id": "verify",
                "description": "Run tests",
                "depends_on": ["implement"],
                "tools": ["Bash"],
                "verification": {
                    "kind": "tests_pass",
                    "command": "python3 -m unittest -v",
                },
            },
        ],
        "risks": ["Do not change tests"],
        "assumptions": [],
        "done_when": "Unit tests pass",
    }
    return final(json.dumps(plan))


def make_project(
    base: Path, name: str = "project", **limits: int
) -> tuple[Path, Path, Path]:
    root = base / name
    workspace = root / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "blocked").mkdir()
    (workspace / "order.py").write_text(BROKEN, encoding="utf-8")
    shutil.copy(ROOT / "workspace" / "test_order.py", workspace / "test_order.py")
    policy_data = json.loads((ROOT / "config" / "policy.json").read_text())
    policy_data["limits"].update(limits)
    policy_file = root / "policy.json"
    policy_file.write_text(json.dumps(policy_data), encoding="utf-8")
    return workspace, policy_file, root / "state.sqlite3"


def make_agent(
    project: tuple[Path, Path, Path],
    answers: list[dict],
    after_tool=None,
) -> Agent:
    workspace, policy_file, state_file = project
    return Agent(workspace, policy_file, state_file, FakeModel(answers), after_tool)


def test_agent_fixes_project_runs_bash_and_preserves_tests(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = make_project(tmp_path)
    workspace = project[0]
    test_hash = hashlib.sha256((workspace / "test_order.py").read_bytes()).hexdigest()
    model = FakeModel(
        [
            plan_reply(),
            tool_reply(
                call("list", "list_files", path="."),
                call("source", "read_file", path="order.py"),
                call("tests", "read_file", path="test_order.py"),
            ),
            tool_reply(
                call("write_bad", "write_file", path="order.py", content=INCOMPLETE)
            ),
            tool_reply(
                call("bash_bad", "Bash", command="python3 -m unittest -v", cwd=".")
            ),
            tool_reply(call("write", "write_file", path="order.py", content=FIXED)),
            tool_reply(
                call("bash_ok", "Bash", command="python3 -m unittest -v", cwd=".")
            ),
            final("Tests passed after correcting the calculation."),
        ]
    )
    agent = Agent(workspace, project[1], project[2], model)

    waiting = agent.start("Fix calculation without touching tests")
    assert waiting["phase"] == "waiting_plan"
    done = agent.approve_plan(waiting["id"], True)

    assert done["phase"] == "completed"
    assert [task["status"] for task in done["tasks"]] == ["completed"] * 3
    assert all(task["evidence"] for task in done["tasks"])
    assert (
        hashlib.sha256((workspace / "test_order.py").read_bytes()).hexdigest()
        == test_hash
    )
    bash_results = [
        json.loads(call["result"])
        for call in done["calls"].values()
        if call["name"] == "Bash"
    ]
    assert bash_results[0]["data"]["exit_code"] != 0
    assert "OK" in bash_results[-1]["data"]["stderr"]
    assert done["answer"] == "Tests passed after correcting the calculation."
    assert {
        call_id for call_id, item in done["calls"].items() if item["name"] == "Bash"
    } == {"bash_bad", "bash_ok"}
    show(done)
    output = capsys.readouterr().out
    assert "Task verify: completed" in output
    assert (
        "Tasks:\n  inspect: completed\n  implement: completed\n  verify: completed"
        in output
    )
    offered = [
        {tool["function"]["name"] for tool in request[1]} for request in model.requests
    ]
    assert {"list_files", "read_file"} in offered
    assert {"write_file"} in offered
    assert offered[-1] == set()
    assert done["tasks"][-1]["evidence"]["tool_call_id"] == "bash_ok"
    final_messages = model.requests[-1][0]
    assert final_messages[-1]["role"] == "system"
    assert "FINAL RESPONSE MODE" in final_messages[-1]["content"]
    assert "Do not return JSON" in final_messages[-1]["content"]


def test_protocol_handles_batches_errors_and_reused_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = make_project(tmp_path)
    count = 0

    def counted(policy, name, arguments, output_limit):
        nonlocal count
        count += 1
        return real_execute(policy, name, arguments, output_limit)

    monkeypatch.setattr(engine_module, "execute", counted)
    agent = make_agent(
        project,
        [
            tool_reply(
                call("same", "read_file", path="order.py"),
                call("invalid", "read_file"),
            ),
            tool_reply(call("same", "read_file", path="order.py")),
            plan_reply(),
        ],
    )
    state = agent.start("Inspect")
    assert state["phase"] == "waiting_plan"
    assert count == 1
    assert json.loads(state["calls"]["invalid"]["result"])["ok"] is False

    mismatch = make_agent(
        make_project(tmp_path, "mismatch"),
        [
            tool_reply(call("same", "read_file", path="order.py")),
            tool_reply(call("same", "read_file", path="test_order.py")),
        ],
    ).start("Inspect")
    assert mismatch["phase"] == "failed"
    assert "protocol error" in mismatch["error"]


def test_plan_accepts_other_files_and_task_counts() -> None:
    one_task = {
        "goal": "Create a settings file",
        "steps": [
            {
                "id": "create",
                "description": "Create settings.py",
                "depends_on": [],
                "tools": ["write_file"],
                "verification": {"kind": "file_changed", "path": "settings.py"},
            }
        ],
        "risks": [],
        "assumptions": [],
        "done_when": "settings.py exists",
    }
    four_tasks = {
        **one_task,
        "steps": [
            {
                "id": f"read_{index}",
                "description": f"Read file {index}",
                "depends_on": [] if index == 0 else [f"read_{index - 1}"],
                "tools": ["read_file"],
                "verification": {
                    "kind": "read_files",
                    "paths": [f"module_{index}.py"],
                },
            }
            for index in range(4)
        ],
    }

    assert len(parse_plan(json.dumps(one_task))["steps"]) == 1
    assert len(parse_plan(json.dumps(four_tasks))["steps"]) == 4


def test_plan_rejects_file_change_after_tests_pass() -> None:
    plan = json.loads(plan_reply()["content"])
    plan["steps"][1]["depends_on"] = ["verify"]
    plan["steps"][2]["depends_on"] = ["inspect"]

    with pytest.raises(AgentError, match="changes files after tests_pass"):
        parse_plan(json.dumps(plan))


@pytest.mark.parametrize(
    "change",
    (
        lambda plan: plan["steps"][0].update(tools=["unknown"]),
        lambda plan: plan["steps"][0].update(depends_on=["missing"]),
        lambda plan: plan["steps"][0].update(depends_on=["create"]),
    ),
    ids=("unknown-tool", "missing-dependency", "dependency-cycle"),
)
def test_plan_rejects_invalid_tools_and_dependencies(change) -> None:
    plan = {
        "goal": "Create a file",
        "steps": [
            {
                "id": "create",
                "description": "Create settings.py",
                "depends_on": [],
                "tools": ["write_file"],
                "verification": {"kind": "file_changed", "path": "settings.py"},
            }
        ],
        "risks": [],
        "assumptions": [],
        "done_when": "File exists",
    }
    change(plan)
    with pytest.raises(AgentError):
        parse_plan(json.dumps(plan))


def test_planner_receives_specific_correction_for_empty_tools(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    invalid_plan = {
        "goal": "Inspect a file",
        "steps": [
            {
                "id": "reason",
                "description": "Think about the source",
                "depends_on": [],
                "tools": [],
                "verification": {
                    "kind": "tests_pass",
                    "command": "python3 -m unittest -v",
                },
            }
        ],
        "risks": [],
        "assumptions": [],
        "done_when": "Tests pass",
    }
    agent = make_agent(project, [final(json.dumps(invalid_plan)), plan_reply()])

    waiting = agent.start("Fix order.py")

    assert waiting["phase"] == "waiting_plan"
    correction = agent.model.requests[1][0][-1]["content"]
    assert "task reason must have at least one tool" in correction
    initial_prompt = agent.model.requests[0][0][-1]["content"]
    assert "Never invent a directory prefix" in initial_prompt
    assert "Reading and testing alone cannot complete" in initial_prompt


@pytest.mark.parametrize(
    ("response", "expected_name"),
    (
        (
            '```json\n{"tool_calls":[{"function":"read_file",'
            '"arguments":{"path":"order.py"}}]}\n```',
            "read_file",
        ),
        ('{"name":"read_file","arguments":{"path":"x.py"}}', "read_file"),
        (
            'I will use: {"name":"read_file","arguments":{"path":"x.py"}}',
            "read_file",
        ),
        ('{"tool_call":"write_file","path":"x.py","content":"value"}', "write_file"),
        ('{"tool":"read_file","path":"x.py"}', "read_file"),
    ),
    ids=("fenced", "direct", "inside-text", "tool-call-alias", "tool-alias"),
)
def test_text_tool_call_formats(response: str, expected_name: str) -> None:
    converted = text_tool_calls(response)
    assert converted[0]["function"]["name"] == expected_name


def test_text_response_can_contain_multiple_tool_calls() -> None:
    several = text_tool_calls(
        '{"name":"write_file","arguments":{"path":"x.py","content":"x"}}\n'
        '{"name":"test","arguments":{}}'
    )
    assert [item["function"]["name"] for item in several] == ["write_file", "test"]


def test_policy_allows_exact_command(tmp_path: Path) -> None:
    workspace, policy_file, _ = make_project(tmp_path)
    policy = Policy(workspace, policy_file)
    assert policy.bash("python3 -m unittest -v", ".") == workspace.resolve()


@pytest.mark.parametrize(
    "command",
    (
        "python3 -m unittest",
        "python3 -m unittest -v | cat",
        "python3 -m unittest -v; pwd",
        "python3 -m unittest -v > result.txt",
        "python3 -m unittest -v $(pwd)",
        "python3 -m unittest -v `pwd`",
        "bash -c pwd",
    ),
)
def test_policy_rejects_command(tmp_path: Path, command: str) -> None:
    workspace, policy_file, _ = make_project(tmp_path)
    with pytest.raises(PolicyError):
        Policy(workspace, policy_file).bash(command, ".")


def test_policy_rejects_allowed_command_in_denied_directory(tmp_path: Path) -> None:
    workspace, policy_file, _ = make_project(tmp_path)
    with pytest.raises(PolicyError):
        Policy(workspace, policy_file).bash("python3 -m unittest -v", "blocked")


@pytest.mark.parametrize("path", ("../outside", "/tmp/outside", "blocked/file.txt"))
def test_policy_rejects_path(tmp_path: Path, path: str) -> None:
    workspace, policy_file, _ = make_project(tmp_path)
    with pytest.raises(PolicyError):
        Policy(workspace, policy_file).path(path)


def test_policy_rejects_protected_file_and_symlink(tmp_path: Path) -> None:
    workspace, policy_file, _ = make_project(tmp_path)
    policy = Policy(workspace, policy_file)
    with pytest.raises(PolicyError, match="protected"):
        policy.path("test_order.py", change=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PolicyError):
        policy.path("link/file.txt")


def test_list_files_hides_denied_directories_and_symlinks(tmp_path: Path) -> None:
    workspace, policy_file, _ = make_project(tmp_path)
    (workspace / "visible.py").write_text("value = 1\n", encoding="utf-8")
    (workspace / "nested").mkdir()
    (workspace / "nested" / "inside.py").write_text("value = 2\n", encoding="utf-8")
    (workspace / "blocked" / "secret.py").write_text("secret = 1\n", encoding="utf-8")
    outside = tmp_path / "outside-files"
    outside.mkdir()
    (outside / "private.py").write_text("private = 1\n", encoding="utf-8")
    (workspace / "external").symlink_to(outside, target_is_directory=True)
    policy = Policy(workspace, policy_file)

    result = real_execute(policy, "list_files", {"path": "."}, output_limit=1000)

    assert "visible.py" in result["files"]
    assert "nested/inside.py" in result["files"]
    assert all(not path.startswith("blocked/") for path in result["files"])
    assert all(not path.startswith("external/") for path in result["files"])
    with pytest.raises(PolicyError):
        real_execute(policy, "list_files", {"path": "blocked"}, output_limit=1000)


def test_delete_requires_approval_and_removes_file(tmp_path: Path) -> None:
    workspace, policy_file, _ = make_project(tmp_path)
    removable = workspace / "temporary.py"
    removable.write_text("value = 1\n", encoding="utf-8")
    policy = Policy(workspace, policy_file)
    assert policy.needs_approval("delete_file", "safe")
    assert policy.needs_approval("delete_file", "auto")
    deleted = real_execute(
        policy, "delete_file", {"path": "temporary.py"}, output_limit=1000
    )
    assert deleted == {"path": "temporary.py", "deleted": True}
    assert not removable.exists()


def test_bash_timeout_stops_process(tmp_path: Path) -> None:
    workspace, policy_file, _ = make_project(tmp_path)
    policy_data = json.loads(policy_file.read_text(encoding="utf-8"))
    policy_data["commands"]["allow"].append("sleep 2")
    policy_data["limits"]["bash_seconds"] = 1
    policy_file.write_text(json.dumps(policy_data), encoding="utf-8")
    timed_out = real_execute(
        Policy(workspace, policy_file),
        "Bash",
        {"command": "sleep 2", "cwd": "."},
        output_limit=1000,
    )
    assert timed_out["timed_out"] is True
    assert timed_out["exit_code"] != 0


def test_bash_limits_output_while_process_is_running(tmp_path: Path) -> None:
    workspace, policy_file, _ = make_project(tmp_path)
    policy_data = json.loads(policy_file.read_text(encoding="utf-8"))
    policy_data["commands"]["allow"].append("seq 1 100000")
    policy_file.write_text(json.dumps(policy_data), encoding="utf-8")

    result = real_execute(
        Policy(workspace, policy_file),
        "Bash",
        {"command": "seq 1 100000", "cwd": "."},
        output_limit=512,
    )

    assert result["exit_code"] == 0
    assert result["timed_out"] is False
    assert result["truncated"] is True
    assert len(result["stdout"].encode()) + len(result["stderr"].encode()) <= 512


def test_plan_mode_blocks_side_effects_and_repairs_invalid_plan(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    agent = make_agent(
        project,
        [
            tool_reply(call("bad", "write_file", path="new.txt", content="x")),
            final("not json"),
            plan_reply(),
        ],
    )
    state = agent.start("Plan a change")
    assert state["phase"] == "waiting_plan"
    assert not (project[0] / "new.txt").exists()
    assert state["used"]["side_effects"] == 0
    assert json.loads(state["calls"]["bad"]["result"])["ok"] is False
    assert all(
        {tool["function"]["name"] for tool in tools} <= {"list_files", "read_file"}
        for _, tools in agent.model.requests
    )

    stuck_project = make_project(tmp_path, "stuck")
    stuck = make_agent(
        stuck_project,
        [
            plan_reply(),
            tool_reply(
                call("a", "read_file", path="order.py"),
                call("b", "read_file", path="test_order.py"),
            ),
            final("Read"),
            final("No change"),
            final("Still no change"),
            final("Done"),
        ],
    )
    waiting = stuck.start("Fix")
    failed = stuck.approve_plan(waiting["id"], True)
    assert failed["phase"] == "failed"
    assert failed["error"] == "task implement has no verified result"
    assert failed["used"]["model_requests"] == 5

    invalid_project = make_project(tmp_path, "invalid-plan")
    invalid = make_agent(
        invalid_project,
        [final("invalid"), final("still invalid"), final("invalid again")],
    ).start("Plan a change")
    assert invalid["phase"] == "failed"
    assert invalid["plan"] is None
    assert "planning failed after 3 attempts" in invalid["error"]


def test_agent_cannot_finish_test_task_without_model_bash_call(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    agent = make_agent(
        project,
        [
            plan_reply(),
            tool_reply(
                call("source", "read_file", path="order.py"),
                call("tests", "read_file", path="test_order.py"),
            ),
            tool_reply(call("write", "write_file", path="order.py", content=FIXED)),
            final("Tests should pass."),
            final("The task is complete."),
            final("Done."),
        ],
    )

    waiting = agent.start("Fix")
    failed = agent.approve_plan(waiting["id"], True)

    assert failed["phase"] == "failed"
    assert failed["error"] == "task verify has no verified result"
    assert all(item["name"] != "Bash" for item in failed["calls"].values())
    assert failed["tasks"][-1]["evidence"] is None


def test_safe_mode_waits_for_write_and_bash_approval(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    agent = make_agent(
        project,
        [
            plan_reply(),
            tool_reply(
                call("a", "read_file", path="order.py"),
                call("b", "read_file", path="test_order.py"),
            ),
            tool_reply(call("write", "write_file", path="order.py", content=FIXED)),
            tool_reply(call("bash", "Bash", command="python3 -m unittest -v", cwd=".")),
            final("Tests passed."),
        ],
    )
    waiting = agent.start("Fix", mode="safe")
    paused = agent.approve_plan(waiting["id"], True)
    assert paused["phase"] == "waiting_action"
    assert (project[0] / "order.py").read_text() == BROKEN
    paused_again = agent.decide_action(waiting["id"], True)
    assert paused_again["phase"] == "waiting_action"
    next_call = paused_again["calls"][paused_again["queue"][0]]
    assert next_call["name"] == "Bash"
    assert (project[0] / "order.py").read_text() == FIXED


def test_safe_mode_rejection_keeps_file_unchanged(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    rejecting = make_agent(
        project,
        [
            plan_reply(),
            tool_reply(
                call("a", "read_file", path="order.py"),
                call("b", "read_file", path="test_order.py"),
            ),
            final("Read"),
            tool_reply(call("write", "write_file", path="order.py", content=FIXED)),
            tool_reply(call("write2", "write_file", path="order.py", content=FIXED)),
        ],
    )
    waiting = rejecting.start("Fix", mode="safe")
    paused = rejecting.approve_plan(waiting["id"], True)
    paused = rejecting.decide_action(paused["id"], False)
    assert paused["phase"] == "waiting_action"
    assert (project[0] / "order.py").read_text() == BROKEN


def test_resume_preserves_budgets_and_completed_tasks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = make_project(tmp_path)
    executed = []

    def recorded(policy, name, arguments, output_limit):
        executed.append(name)
        return real_execute(policy, name, arguments, output_limit)

    monkeypatch.setattr(engine_module, "execute", recorded)
    agent = make_agent(
        project,
        [
            plan_reply(),
            tool_reply(
                call("source", "read_file", path="order.py"),
                call("tests", "read_file", path="test_order.py"),
            ),
            tool_reply(call("write", "write_file", path="order.py", content=FIXED)),
        ],
    )
    waiting_plan = agent.start("Fix", mode="safe")
    waiting_write = agent.approve_plan(waiting_plan["id"], True)
    assert waiting_write["phase"] == "waiting_action"
    assert executed == ["read_file", "read_file"]
    used_before_resume = dict(waiting_write["used"])

    restarted = make_agent(
        project,
        [tool_reply(call("bash", "Bash", command="python3 -m unittest -v", cwd="."))],
    )
    resumed = restarted.drive(waiting_plan["id"])
    assert resumed["used"] == used_before_resume
    assert resumed["tasks"][0]["status"] == "completed"
    assert executed == ["read_file", "read_file"]

    waiting_bash = restarted.decide_action(waiting_plan["id"], True)
    assert waiting_bash["phase"] == "waiting_action"
    used_before_second_resume = dict(waiting_bash["used"])
    restarted_again = make_agent(project, [final("Tests passed.")])
    resumed_again = restarted_again.drive(waiting_plan["id"])
    assert resumed_again["used"] == used_before_second_resume
    assert executed == ["read_file", "read_file", "write_file"]

    completed = restarted_again.decide_action(waiting_plan["id"], True)
    assert completed["phase"] == "completed"
    assert [task["status"] for task in completed["tasks"]] == ["completed"] * 3
    assert executed == ["read_file", "read_file", "write_file", "Bash"]


def test_crash_becomes_uncertain_and_is_not_repeated(tmp_path: Path) -> None:
    project = make_project(tmp_path)

    def crash(tool: dict) -> None:
        if tool["name"] == "write_file":
            raise RuntimeError("injected crash")

    agent = make_agent(
        project,
        [
            plan_reply(),
            tool_reply(
                call("a", "read_file", path="order.py"),
                call("b", "read_file", path="test_order.py"),
            ),
            final("Read"),
            tool_reply(call("write", "write_file", path="order.py", content=FIXED)),
        ],
        crash,
    )
    waiting = agent.start("Fix")
    with pytest.raises(RuntimeError, match="injected"):
        agent.approve_plan(waiting["id"], True)
    recovered = make_agent(project, []).drive(waiting["id"])
    assert recovered["phase"] == "uncertain"
    assert recovered["used"]["side_effects"] == 1
    assert len(recovered["calls"]["write"]["attempts"]) == 1
    stopped = make_agent(project, []).resolve(waiting["id"], "abort")
    assert stopped["phase"] == "failed"


def test_retry_checks_hash_and_creates_a_new_attempt(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    crashed = False

    def crash_once(tool: dict) -> None:
        nonlocal crashed
        if tool["name"] == "write_file" and not crashed:
            crashed = True
            raise RuntimeError("crash")

    answers = [
        plan_reply(),
        tool_reply(
            call("a", "read_file", path="order.py"),
            call("b", "read_file", path="test_order.py"),
        ),
        tool_reply(call("write", "write_file", path="order.py", content=FIXED)),
        tool_reply(call("bash", "Bash", command="python3 -m unittest -v", cwd=".")),
        final("Passed"),
    ]
    agent = make_agent(project, answers, crash_once)
    waiting = agent.start("Fix")
    with pytest.raises(RuntimeError):
        agent.approve_plan(waiting["id"], True)
    agent.drive(waiting["id"])
    done = agent.resolve(waiting["id"], "retry")
    assert done["phase"] == "completed"
    assert len(done["calls"]["write"]["attempts"]) == 2
    assert done["used"]["side_effects"] == 3

    unsafe_project = make_project(tmp_path, "unsafe")

    def unsafe_crash(tool: dict) -> None:
        if tool["name"] == "write_file":
            raise RuntimeError("crash")

    unsafe = make_agent(unsafe_project, answers[:4], unsafe_crash)
    waiting = unsafe.start("Fix")
    with pytest.raises(RuntimeError):
        unsafe.approve_plan(waiting["id"], True)
    unsafe.drive(waiting["id"])
    (unsafe_project[0] / "order.py").write_text("external", encoding="utf-8")
    with pytest.raises(AgentError, match="externally"):
        unsafe.resolve(waiting["id"], "retry")


def test_uncertain_call_can_be_marked_failed_and_replaced(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    crashed = False

    def crash_first_write(tool: dict) -> None:
        nonlocal crashed
        if tool["name"] == "write_file" and not crashed:
            crashed = True
            raise RuntimeError("crash")

    agent = make_agent(
        project,
        [
            plan_reply(),
            tool_reply(
                call("source", "read_file", path="order.py"),
                call("tests", "read_file", path="test_order.py"),
            ),
            tool_reply(call("uncertain", "write_file", path="order.py", content=FIXED)),
            tool_reply(
                call("replacement", "write_file", path="order.py", content=FIXED + "\n")
            ),
            tool_reply(call("bash", "Bash", command="python3 -m unittest -v", cwd=".")),
            final("Recovered and passed."),
        ],
        crash_first_write,
    )
    waiting = agent.start("Fix")
    with pytest.raises(RuntimeError, match="crash"):
        agent.approve_plan(waiting["id"], True)
    assert agent.drive(waiting["id"])["phase"] == "uncertain"

    completed = agent.resolve(waiting["id"], "fail")
    assert completed["phase"] == "completed"
    assert len(completed["calls"]["uncertain"]["attempts"]) == 1
    failed_result = json.loads(completed["calls"]["uncertain"]["result"])
    assert failed_result["ok"] is False
    assert completed["calls"]["replacement"]["status"] == "completed"


def test_model_request_budget_stops_run(tmp_path: Path) -> None:
    project = make_project(tmp_path, model_requests=1)
    agent = make_agent(project, [plan_reply()])
    waiting = agent.start("Fix")
    exhausted = agent.approve_plan(waiting["id"], True)
    assert exhausted["phase"] == "budget_exhausted"
    assert exhausted["used"]["model_requests"] == 1


def test_tool_call_budget_rejects_whole_batch(tmp_path: Path) -> None:
    project = make_project(tmp_path, tool_calls=1)
    exhausted = make_agent(
        project,
        [
            tool_reply(
                call("a", "read_file", path="order.py"),
                call("b", "read_file", path="test_order.py"),
            )
        ],
    ).start("Inspect")
    assert exhausted["phase"] == "budget_exhausted"
    assert exhausted["used"]["tool_calls"] == 0
    assert exhausted["calls"] == {}


def test_side_effect_budget_rejects_whole_batch(tmp_path: Path) -> None:
    project = make_project(tmp_path, side_effects=1)
    agent = make_agent(
        project,
        [
            plan_reply(),
            tool_reply(
                call("a", "read_file", path="order.py"),
                call("b", "read_file", path="test_order.py"),
            ),
            final("Read"),
            tool_reply(
                call("x", "write_file", path="order.py", content=FIXED),
                call("y", "write_file", path="copy.py", content=FIXED),
            ),
        ],
    )
    waiting = agent.start("Fix")
    exhausted = agent.approve_plan(waiting["id"], True)
    assert exhausted["phase"] == "budget_exhausted"
    assert exhausted["used"]["side_effects"] == 0
    assert (project[0] / "order.py").read_text() == BROKEN


def test_output_budget_truncates_tool_result(tmp_path: Path) -> None:
    project = make_project(
        tmp_path,
        tool_output_bytes=150,
        single_result_bytes=150,
    )
    exhausted = make_agent(
        project,
        [tool_reply(call("read", "read_file", path="test_order.py")), plan_reply()],
    ).start("Inspect")
    result = json.loads(exhausted["calls"]["read"]["result"])
    assert result["truncated"] is True
    assert exhausted["used"]["tool_output_bytes"] <= 150


def test_sqlite_conflict_prevents_two_writers(tmp_path: Path) -> None:
    store = Store(tmp_path / "state.sqlite3")
    state = {"id": "run", "value": 0}
    store.create(state)
    first = store.load("run")
    second = store.load("run")
    first["value"] = 1
    store.save(first)
    second["value"] = 2
    with pytest.raises(StateConflict):
        store.save(second)
    assert store.load("run")["value"] == 1
