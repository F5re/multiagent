import hashlib
import json
import uuid
from pathlib import Path

from agent.policy import Policy
from agent.storage import Store
from agent.tools import SCHEMAS, SIDE_EFFECTS, definitions, execute, file_hash, validate


class AgentError(RuntimeError):
    pass


VERIFY_TOOL = {
    "read_files": "read_file",
    "file_changed": "write_file",
    "file_deleted": "delete_file",
    "tests_pass": "Bash",
}


def parse_plan(text: str) -> dict:
    try:
        plan = json.loads(text)
    except json.JSONDecodeError as error:
        raise AgentError("plan must be valid JSON") from error
    if not isinstance(plan, dict) or set(plan) != {
        "goal",
        "steps",
        "risks",
        "assumptions",
        "done_when",
    }:
        raise AgentError("plan has invalid fields")
    if not isinstance(plan["goal"], str) or not plan["goal"]:
        raise AgentError("plan goal is required")
    if not isinstance(plan["done_when"], str) or not plan["done_when"]:
        raise AgentError("plan completion criterion is required")
    for field in ("risks", "assumptions"):
        if not isinstance(plan[field], list) or not all(
            isinstance(item, str) for item in plan[field]
        ):
            raise AgentError(f"plan {field} must contain strings")
    steps = plan["steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= 20:
        raise AgentError("plan must contain between one and twenty tasks")
    known: set[str] = set()
    for step in steps:
        if not isinstance(step, dict) or set(step) != {
            "id",
            "description",
            "depends_on",
            "tools",
            "verification",
        }:
            raise AgentError("plan task has invalid fields")
        task_id = step["id"]
        if not isinstance(task_id, str) or not task_id or task_id in known:
            raise AgentError("task ids must be unique strings")
        if not isinstance(step["description"], str) or not step["description"]:
            raise AgentError("task description is required")
        dependencies = step["depends_on"]
        if not isinstance(dependencies, list) or not all(
            isinstance(item, str) for item in dependencies
        ):
            raise AgentError("task dependencies must contain ids")
        if len(dependencies) != len(set(dependencies)):
            raise AgentError("task dependencies must be unique")
        tools = step["tools"]
        if not isinstance(tools, list) or not tools:
            raise AgentError(f"task {task_id} must have at least one tool")
        if not all(isinstance(item, str) for item in tools):
            raise AgentError(f"task {task_id} contains unknown tools")
        unknown_tools = [item for item in tools if item not in SCHEMAS]
        if unknown_tools:
            raise AgentError(
                f"task {task_id} contains unknown tools: {', '.join(unknown_tools)}"
            )
        proof = step["verification"]
        if not isinstance(proof, dict) or proof.get("kind") not in VERIFY_TOOL:
            raise AgentError("task verification is invalid")
        kind = proof["kind"]
        key = (
            "paths"
            if kind == "read_files"
            else "command"
            if kind == "tests_pass"
            else "path"
        )
        if set(proof) != {"kind", key}:
            raise AgentError("task verification fields are invalid")
        value = proof[key]
        if kind == "read_files":
            if (
                not isinstance(value, list)
                or not value
                or not all(isinstance(item, str) and item for item in value)
            ):
                raise AgentError("read_files requires paths")
        elif not isinstance(value, str) or not value:
            raise AgentError(f"{kind} requires {key}")
        if VERIFY_TOOL[kind] not in tools:
            raise AgentError(
                f"task {task_id} verification requires {VERIFY_TOOL[kind]}"
            )
        known.add(task_id)
    dependencies = {step["id"]: set(step["depends_on"]) for step in steps}
    if any(task_id in required for task_id, required in dependencies.items()):
        raise AgentError("task cannot depend on itself")
    if any(not required <= known for required in dependencies.values()):
        raise AgentError("dependencies must reference existing tasks")
    remaining = dict(dependencies)
    resolved: set[str] = set()
    while remaining:
        ready = [
            task_id for task_id, required in remaining.items() if required <= resolved
        ]
        if not ready:
            raise AgentError("task dependencies contain a cycle")
        resolved.update(ready)
        for task_id in ready:
            del remaining[task_id]
    by_id = {step["id"]: step for step in steps}
    for step in steps:
        if step["verification"]["kind"] not in {"file_changed", "file_deleted"}:
            continue
        ancestors = list(step["depends_on"])
        for task_id in ancestors:
            dependency = by_id[task_id]
            if dependency["verification"]["kind"] == "tests_pass":
                raise AgentError(
                    f"task {step['id']} changes files after tests_pass task {task_id}"
                )
            ancestors.extend(
                item for item in dependency["depends_on"] if item not in ancestors
            )
    return plan


class Agent:
    def __init__(
        self,
        workspace: Path,
        policy_file: Path,
        state_file: Path,
        model,
        after_tool=None,
    ) -> None:
        self.policy = Policy(workspace, policy_file)
        self.store = Store(state_file)
        self.model = model
        self.after_tool = after_tool

    def start(self, request: str, mode: str = "auto") -> dict:
        if not request.strip():
            raise ValueError("request must not be empty")
        if mode not in {"safe", "auto"}:
            raise ValueError("mode must be safe or auto")
        run_id = uuid.uuid4().hex
        state = {
            "id": run_id,
            "request": request,
            "mode": mode,
            "phase": "planning",
            "plan": None,
            "plan_errors": 0,
            "tasks": [],
            "calls": {},
            "queue": [],
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a coding agent. Use tools, never invent results, "
                        "and do not edit tests. Answer concisely."
                    ),
                },
                {"role": "user", "content": request},
                {
                    "role": "system",
                    "content": (
                        "PLAN MODE. Inspect only when needed, then return only JSON "
                        "with goal, steps, risks, assumptions, done_when. Use one "
                        "to twenty tasks suited to the request. Each task has id, "
                        "description, depends_on, tools, verification. "
                        "Every task must have at least one tool. Do not create "
                        "analysis-only tasks: include reasoning in a task that "
                        "reads or changes a file. Use paths from the user request "
                        "or paths discovered with reading tools. Never invent a "
                        "directory prefix. The plan must include every side effect "
                        "needed by the request. If the user asks to fix, edit, or "
                        "create code, include a write_file task with file_changed "
                        "verification before any tests_pass task. Reading and "
                        "testing alone cannot complete a code-change request. Use "
                        "tests_pass only for a final successful test after planned "
                        "file changes, never for a diagnostic test before a fix. "
                        "Verification forms: "
                        '{"kind":"read_files","paths":["module.py"]} requires '
                        "read_file in tools; "
                        '{"kind":"file_changed","path":"module.py"} requires '
                        "write_file in tools; "
                        '{"kind":"file_deleted","path":"old.py"}, '
                        "requires delete_file in tools; "
                        '{"kind":"tests_pass","command":"python3 -m unittest -v"} '
                        "requires Bash in tools. "
                        "Use exact tool names: list_files, read_file, write_file, "
                        "delete_file, Bash."
                    ),
                },
            ],
            "limits": {
                key: self.policy.limits[key]
                for key in (
                    "model_requests",
                    "tool_calls",
                    "side_effects",
                    "tool_output_bytes",
                )
            },
            "used": {
                "model_requests": 0,
                "tool_calls": 0,
                "side_effects": 0,
                "tool_output_bytes": 0,
            },
            "answer": None,
            "error": None,
        }
        self.store.create(state)
        return self.drive(run_id)

    def drive(self, run_id: str) -> dict:
        state = self.store.load(run_id)
        started = [
            call for call in state["calls"].values() if call["status"] == "started"
        ]
        if started:
            for call in started:
                call["status"] = "uncertain"
            state["phase"] = "uncertain"
            self.store.save(state)
            return state
        if state["phase"] not in {"planning", "running"}:
            return state
        state["error"] = None
        for _ in range(200):
            if state["queue"]:
                self._process_queue(state)
            if state["phase"] not in {"planning", "running"}:
                return state
            if state["queue"]:
                continue
            if state["phase"] == "running":
                task = self._current_task(state)
                evidence = self._verify(state, task) if task else None
                if task and evidence:
                    task["status"] = "completed"
                    task["evidence"] = evidence
                    self._announce(task, "completed")
                    self.store.save(state)
                    continue
                if task is None:
                    if not all(
                        item["status"] == "completed" for item in state["tasks"]
                    ):
                        state["phase"] = "failed"
                        state["error"] = "no task has satisfied dependencies"
                        self.store.save(state)
                        return state
                    if not state.get("final_prompted"):
                        state["final_prompted"] = True
                        state["messages"].append(
                            {
                                "role": "system",
                                "content": (
                                    "FINAL RESPONSE MODE. All task results are "
                                    "verified. Return a concise natural-language "
                                    "summary of the completed work and test result. "
                                    "Do not return JSON, a plan, or tool calls."
                                ),
                            }
                        )
                        self.store.save(state)
                if task and not task["prompted"]:
                    task["status"] = "running"
                    task["prompted"] = True
                    state["messages"].append(
                        {
                            "role": "user",
                            "content": (
                                f"Current task {task['id']}: {task['description']}. "
                                "Required evidence: "
                                f"{json.dumps(task['verification'])}. "
                                f"Call {VERIFY_TOOL[task['verification']['kind']]} "
                                "using tool_calls and finish only after evidence "
                                "exists. Do not print a tool call as text."
                            ),
                        }
                    )
                    self._announce(task, "started")
                    self.store.save(state)
            self._ask_model(state)
            if state["error"]:
                return state
        state["phase"] = "failed"
        state["error"] = "agent loop safety limit reached"
        self.store.save(state)
        return state

    def _ask_model(self, state: dict) -> None:
        if state["used"]["model_requests"] >= state["limits"]["model_requests"]:
            self._budget_error(state, "model_requests")
            return
        state["used"]["model_requests"] += 1
        self.store.save(state)
        planning = state["phase"] == "planning"
        task = self._current_task(state) if not planning else None
        permitted = set(task["tools"]) if task else set() if not planning else None
        offered = definitions(planning, permitted)
        try:
            reply = self.model.complete(state["messages"], offered, planning)
        except Exception as error:
            state["error"] = f"model request failed: {error}"
            self.store.save(state)
            return
        if not isinstance(reply, dict):
            state["error"] = "model returned an invalid message"
            self.store.save(state)
            return
        calls = reply.get("tool_calls") or []
        if not isinstance(calls, list):
            state["error"] = "model tool_calls must be an array"
            self.store.save(state)
            return
        state["messages"].append(
            {
                "role": "assistant",
                "content": reply.get("content"),
                **({"tool_calls": calls} if calls else {}),
            }
        )
        if calls:
            if not planning and task is None:
                self._protocol_error(state, "tools cannot run after all tasks complete")
                return
            self._queue_calls(state, calls)
            return
        content = reply.get("content")
        if not isinstance(content, str) or not content.strip():
            if task:
                self._retry_task(state, task)
            else:
                state["messages"].append(
                    {
                        "role": "user",
                        "content": "Return tool calls or a nonempty response.",
                    }
                )
                self.store.save(state)
            return
        if planning:
            try:
                state["plan"] = parse_plan(content)
            except AgentError as error:
                state["plan_errors"] = state.get("plan_errors", 0) + 1
                if state["plan_errors"] >= 3:
                    state["phase"] = "failed"
                    state["error"] = f"planning failed after 3 attempts: {error}"
                    self.store.save(state)
                    return
                state["messages"].append(
                    {
                        "role": "user",
                        "content": f"Invalid plan: {error}. Return corrected JSON.",
                    }
                )
                self.store.save(state)
                return
            state["phase"] = "waiting_plan"
            self.store.save(state)
            return
        task = self._current_task(state)
        evidence = self._verify(state, task) if task else None
        if task and evidence is None:
            self._retry_task(state, task)
            return
        if task:
            task["status"] = "completed"
            task["evidence"] = evidence
            self._announce(task, "completed")
        if all(item["status"] == "completed" for item in state["tasks"]):
            state["phase"] = "completed"
            state["answer"] = content
        self.store.save(state)

    def _retry_task(self, state: dict, task: dict) -> None:
        task["repair_attempts"] = task.get("repair_attempts", 0) + 1
        if task["repair_attempts"] >= 3:
            state["phase"] = "failed"
            state["error"] = f"task {task['id']} has no verified result"
        else:
            required = VERIFY_TOOL[task["verification"]["kind"]]
            state["messages"].append(
                {
                    "role": "user",
                    "content": (
                        f"The task is not verified. Call {required} through "
                        "tool_calls with valid arguments. Do not describe the call."
                    ),
                }
            )
        self.store.save(state)

    def _queue_calls(self, state: dict, raw_calls: list[dict]) -> None:
        parsed = []
        seen = set()
        for raw in raw_calls:
            if (
                not isinstance(raw, dict)
                or not isinstance(raw.get("id"), str)
                or not raw["id"]
            ):
                self._protocol_error(state, "tool_call_id is required")
                return
            call_id = raw["id"]
            if call_id in seen:
                self._protocol_error(state, "duplicate tool_call_id in one batch")
                return
            seen.add(call_id)
            function = raw.get("function")
            if not isinstance(function, dict):
                self._protocol_error(state, "tool function is required")
                return
            name = function.get("name")
            try:
                arguments = json.loads(function.get("arguments", ""))
            except (TypeError, json.JSONDecodeError):
                arguments = None
            parsed.append((call_id, name, arguments))
        new_calls = []
        for call_id, name, arguments in parsed:
            previous = state["calls"].get(call_id)
            if previous:
                if previous["name"] != name or previous["arguments"] != arguments:
                    self._protocol_error(
                        state, "tool_call_id was reused with different arguments"
                    )
                    return
            else:
                new_calls.append((call_id, name, arguments))
        if state["used"]["tool_calls"] + len(new_calls) > state["limits"]["tool_calls"]:
            self._budget_error(state, "tool_calls batch")
            return
        side_count = sum(name in SIDE_EFFECTS for _, name, _ in new_calls)
        if state["used"]["side_effects"] + side_count > state["limits"]["side_effects"]:
            self._budget_error(state, "side_effects batch")
            return
        remaining = (
            state["limits"]["tool_output_bytes"] - state["used"]["tool_output_bytes"]
        )
        slot = min(
            self.policy.limits["single_result_bytes"],
            remaining // max(1, len(new_calls)),
        )
        if new_calls and slot < 100:
            self._budget_error(state, "tool_output_bytes batch")
            return
        task = self._current_task(state) if state["phase"] == "running" else None
        state["used"]["tool_calls"] += len(new_calls)
        state["used"]["tool_output_bytes"] += slot * len(new_calls)
        for call_id, name, arguments in parsed:
            if call_id not in state["calls"]:
                state["calls"][call_id] = {
                    "id": call_id,
                    "name": name,
                    "arguments": arguments,
                    "task_id": task["id"] if task else None,
                    "status": "queued",
                    "attempts": [],
                    "result": None,
                    "reserved_output": slot,
                }
            state["queue"].append(call_id)
        self.store.save(state)

    def _process_queue(self, state: dict) -> None:
        while state["queue"] and state["phase"] in {"planning", "running"}:
            call = state["calls"][state["queue"][0]]
            if call["status"] == "completed":
                self._append_cached(state, call)
                continue
            if call["status"] == "started":
                call["status"] = "uncertain"
                state["phase"] = "uncertain"
                self.store.save(state)
                return
            try:
                validate(call["name"], call["arguments"])
                self.policy.check(
                    call["name"],
                    call["arguments"],
                    planning=state["phase"] == "planning",
                )
                task = (
                    self._current_task(state) if state["phase"] == "running" else None
                )
                if task and call["name"] not in task["tools"]:
                    raise ValueError("tool is not allowed for the current task")
            except (ValueError, TypeError, KeyError) as error:
                self._finish_call(state, call, {"ok": False, "error": str(error)})
                continue
            if (
                self.policy.needs_approval(call["name"], state["mode"])
                and call["status"] != "approved"
            ):
                call["status"] = "waiting_approval"
                state["phase"] = "waiting_action"
                self.store.save(state)
                return
            self._perform(state, call)

    def _perform(self, state: dict, call: dict) -> None:
        if call["name"] in SIDE_EFFECTS and not call.pop("retry_reserved", False):
            if state["used"]["side_effects"] >= state["limits"]["side_effects"]:
                self._budget_error(state, "side_effects")
                return
            state["used"]["side_effects"] += 1
        attempt = {"number": len(call["attempts"]) + 1, "status": "started"}
        if call["name"] == "write_file":
            target = self.policy.path(call["arguments"]["path"], change=True)
            attempt["before_sha256"] = file_hash(target)
        call["attempts"].append(attempt)
        call["status"] = "started"
        self.store.save(state)
        try:
            data = execute(
                self.policy,
                call["name"],
                call["arguments"],
                call["reserved_output"],
            )
            payload = {"ok": True, "data": data}
        except Exception as error:
            payload = {"ok": False, "error": f"{type(error).__name__}: {error}"}
        if self.after_tool:
            self.after_tool(call)
        self._finish_call(state, call, payload)

    def _finish_call(self, state: dict, call: dict, payload: dict) -> None:
        content = self._fit_result(payload, call["reserved_output"])
        actual = len(content.encode("utf-8"))
        state["used"]["tool_output_bytes"] -= call["reserved_output"] - actual
        call["reserved_output"] = actual
        call["result"] = content
        call["status"] = "completed"
        if call["attempts"] and call["attempts"][-1]["status"] == "started":
            call["attempts"][-1]["status"] = "completed"
        state["messages"].append(
            {"role": "tool", "tool_call_id": call["id"], "content": content}
        )
        self._reopen_change_after_failed_tests(state, call, payload)
        self._request_missing_file(state, call)
        state["queue"].pop(0)
        self.store.save(state)

    @staticmethod
    def _reopen_change_after_failed_tests(
        state: dict, call: dict, payload: dict
    ) -> None:
        data = payload.get("data", {})
        if (
            call["name"] != "Bash"
            or not payload.get("ok")
            or data.get("exit_code") == 0
        ):
            return
        test_task = next(
            (item for item in state["tasks"] if item["id"] == call["task_id"]),
            None,
        )
        if not test_task or test_task["verification"]["kind"] != "tests_pass":
            return
        change_task = next(
            (
                item
                for item in state["tasks"]
                if item["id"] in test_task["depends_on"]
                and item["verification"]["kind"] == "file_changed"
            ),
            None,
        )
        if not change_task:
            return
        for old_call in state["calls"].values():
            if old_call["task_id"] == change_task["id"]:
                old_call["task_id"] = None
        change_task.update(
            status="pending", prompted=False, repair_attempts=0, evidence=None
        )
        test_task.update(
            status="pending", prompted=False, repair_attempts=0, evidence=None
        )

    @staticmethod
    def _request_missing_file(state: dict, call: dict) -> None:
        if call["name"] != "read_file":
            return
        task = next(
            (item for item in state["tasks"] if item["id"] == call["task_id"]),
            None,
        )
        if not task or task["verification"]["kind"] != "read_files":
            return
        read_paths = {
            item["arguments"]["path"]
            for item in state["calls"].values()
            if item["task_id"] == task["id"]
            and item["name"] == "read_file"
            and item["status"] == "completed"
            and json.loads(item["result"]).get("ok")
        }
        missing = [
            path for path in task["verification"]["paths"] if path not in read_paths
        ]
        if missing:
            state["messages"].append(
                {
                    "role": "user",
                    "content": "Now call read_file for: " + ", ".join(missing),
                }
            )

    def _append_cached(self, state: dict, call: dict) -> None:
        state["messages"].append(
            {"role": "tool", "tool_call_id": call["id"], "content": call["result"]}
        )
        state["queue"].pop(0)
        self.store.save(state)

    @staticmethod
    def _fit_result(payload: dict, room: int) -> str:
        content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(content.encode("utf-8")) <= room:
            return content
        raw = content.encode("utf-8")[: max(0, room - 70)].decode(
            "utf-8", errors="ignore"
        )
        while True:
            shortened = json.dumps(
                {"ok": payload.get("ok", False), "truncated": True, "preview": raw},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            if len(shortened.encode("utf-8")) <= room:
                return shortened
            raw = raw[:-1]

    def _verify(self, state: dict, task: dict) -> dict | None:
        proof = task["verification"]
        calls = []
        for call in state["calls"].values():
            if call["task_id"] != task["id"] or call["status"] != "completed":
                continue
            result = json.loads(call["result"])
            if result.get("ok"):
                calls.append((call, result.get("data", {})))
        kind = proof["kind"]
        if kind == "read_files":
            found = {
                call["arguments"]["path"]
                for call, _ in calls
                if call["name"] == "read_file"
            }
            if set(proof["paths"]) <= found:
                return {"tool_call_ids": [call["id"] for call, _ in calls]}
        if kind == "file_changed":
            target = self.policy.path(proof["path"])
            for call, data in calls:
                if (
                    call["name"] == "write_file"
                    and call["arguments"]["path"] == proof["path"]
                    and call["attempts"][0].get("before_sha256")
                    != data.get("after_sha256")
                    and file_hash(target) == data.get("after_sha256")
                ):
                    return {
                        "tool_call_id": call["id"],
                        "sha256": data["after_sha256"],
                    }
        if kind == "file_deleted":
            for call, _ in calls:
                if (
                    call["name"] == "delete_file"
                    and call["arguments"]["path"] == proof["path"]
                    and not self.policy.path(proof["path"]).exists()
                ):
                    return {"tool_call_id": call["id"], "deleted": True}
        if kind == "tests_pass":
            for call, data in calls:
                if (
                    call["name"] == "Bash"
                    and call["arguments"]["command"] == proof["command"]
                    and data.get("exit_code") == 0
                    and not data.get("timed_out")
                ):
                    return {"tool_call_id": call["id"], "exit_code": 0}
        return None

    @staticmethod
    def _current_task(state: dict) -> dict | None:
        completed = {
            task["id"] for task in state["tasks"] if task["status"] == "completed"
        }
        for task in state["tasks"]:
            if task["status"] != "completed" and set(task["depends_on"]) <= completed:
                return task
        return None

    @staticmethod
    def _announce(task: dict, event: str) -> None:
        print(f"Task {task['id']}: {event}")

    def approve_plan(self, run_id: str, approved: bool) -> dict:
        state = self.store.load(run_id)
        if state["phase"] != "waiting_plan":
            raise AgentError("run is not waiting for plan approval")
        if not approved:
            state["phase"] = "rejected"
            self.store.save(state)
            return state
        state["tasks"] = [
            {
                "id": step["id"],
                "description": step["description"],
                "depends_on": step["depends_on"],
                "tools": step["tools"],
                "verification": step["verification"],
                "status": "pending",
                "prompted": False,
                "repair_attempts": 0,
                "evidence": None,
            }
            for step in state["plan"]["steps"]
        ]
        state["phase"] = "running"
        state["messages"].append(
            {
                "role": "system",
                "content": (
                    "EXECUTION MODE. Plan Mode has ended and the approved plan is "
                    "fixed. Execute its tasks in dependency order using only the "
                    "offered tools. Do not create or return another plan."
                ),
            }
        )
        self.store.save(state)
        return self.drive(run_id)

    def decide_action(self, run_id: str, approved: bool) -> dict:
        state = self.store.load(run_id)
        if state["phase"] != "waiting_action" or not state["queue"]:
            raise AgentError("run is not waiting for action approval")
        call = state["calls"][state["queue"][0]]
        state["phase"] = "running"
        if approved:
            call["status"] = "approved"
            self.store.save(state)
        else:
            self._finish_call(
                state, call, {"ok": False, "error": "action rejected by user"}
            )
        return self.drive(run_id)

    def resolve(self, run_id: str, decision: str) -> dict:
        state = self.store.load(run_id)
        if state["phase"] != "uncertain" or not state["queue"]:
            raise AgentError("run has no uncertain action")
        call = state["calls"][state["queue"][0]]
        if decision == "abort":
            state["phase"] = "failed"
            state["error"] = "user aborted an uncertain action"
            self.store.save(state)
            return state
        if decision == "fail":
            state["phase"] = "running"
            self._finish_call(
                state, call, {"ok": False, "error": "uncertain action marked failed"}
            )
            return self.drive(run_id)
        if decision != "retry" or call["name"] != "write_file":
            raise AgentError("only write_file supports retry")
        target = self.policy.path(call["arguments"]["path"], change=True)
        current = file_hash(target)
        previous = call["attempts"][-1].get("before_sha256")
        wanted = hashlib.sha256(
            call["arguments"]["content"].encode("utf-8")
        ).hexdigest()
        if current not in {previous, wanted}:
            raise AgentError("file changed externally; retry is unsafe")
        if state["used"]["side_effects"] >= state["limits"]["side_effects"]:
            self._budget_error(state, "side_effects")
            return state
        state["used"]["side_effects"] += 1
        call["retry_reserved"] = True
        call["status"] = "approved"
        call["attempts"][-1]["status"] = "unknown"
        state["phase"] = "running"
        self.store.save(state)
        return self.drive(run_id)

    def _budget_error(self, state: dict, name: str) -> None:
        state["phase"] = "budget_exhausted"
        state["error"] = f"{name} budget exhausted"
        self.store.save(state)

    def _protocol_error(self, state: dict, message: str) -> None:
        state["phase"] = "failed"
        state["error"] = "protocol error: " + message
        self.store.save(state)
