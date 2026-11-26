import hashlib
import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from agent.engine import Agent
from agent.model import ChatModel


class EvalError(RuntimeError):
    pass


class EvalRunner:
    def __init__(
        self,
        root: Path,
        cases_file: Path,
        output: Path,
        model_factory: Callable[[], object] = ChatModel,
        variant_skills: dict[str, tuple[bool, Path]] | None = None,
    ) -> None:
        self.root = root
        self.cases_file = cases_file
        self.output = output
        self.model_factory = model_factory
        self.variant_skills = variant_skills or {
            "A": (False, root / "skills"),
            "B": (True, root / "skills"),
        }
        self.cases = self._load_cases()
        self.results_file = output / "results.jsonl"

    def _load_cases(self) -> list[dict]:
        try:
            cases = json.loads(self.cases_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvalError("could not read eval cases") from error
        if not isinstance(cases, list) or not cases:
            raise EvalError("eval cases must be a nonempty array")
        required = {
            "id",
            "request",
            "fixture",
            "checker",
            "expected_skill",
            "required_tools",
        }
        for case in cases:
            if not isinstance(case, dict) or not required <= set(case):
                raise EvalError("eval case has invalid fields")
        return cases

    def run(self, trials: int = 3) -> list[dict]:
        if trials <= 0:
            raise EvalError("trials must be positive")
        self.output.mkdir(parents=True, exist_ok=True)
        results = self.read_results()
        completed = {
            (item["case_id"], item["variant"], item["trial"]) for item in results
        }
        for case in self.cases:
            for trial in range(1, trials + 1):
                for variant in self.variant_skills:
                    key = (case["id"], variant, trial)
                    if key in completed:
                        print(f"[eval] Skip saved trial: {case['id']} {variant}{trial}")
                        continue
                    print(f"[eval] Run {case['id']} {variant}{trial}")
                    result = self._trial(case, variant, trial)
                    with self.results_file.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(result, ensure_ascii=False) + "\n")
                    results.append(result)
                    self.write_summary(results)
        return results

    def _trial(self, case: dict, variant: str, trial: int) -> dict:
        trial_root = self.output / case["id"] / variant / str(trial)
        if trial_root.exists():
            shutil.rmtree(trial_root)
        workspace = trial_root / "workspace"
        shutil.copytree(self.root / case["fixture"], workspace)
        state_file = trial_root / "state.sqlite3"
        agent = Agent(
            workspace,
            self.root / "config" / "policy.json",
            state_file,
            self.model_factory(),
            skills_dir=self.variant_skills[variant][1],
            skills_enabled=self.variant_skills[variant][0],
            mcp_config=self.root / "config" / "mcp.json",
        )
        session_id = agent.store.create_session()
        try:
            state = agent.start(case["request"], "auto", session_id)
            for _ in range(50):
                if state["phase"] == "waiting_plan":
                    state = agent.approve_plan(state["id"], True)
                elif state["phase"] == "waiting_action":
                    state = agent.decide_action(state["id"], True)
                elif state["phase"] == "uncertain":
                    state = agent.resolve(state["id"], "fail")
                else:
                    break
            error = state.get("error")
        except Exception as exception:
            state = {"id": "not-created", "phase": "failed", "usage": {}}
            error = f"{type(exception).__name__}: {exception}"
        events_file = trial_root / "events.jsonl"
        agent.store.export_events(session_id, events_file)
        events = agent.store.events(session_id)
        outcome = check_result(case["checker"], workspace, state, events)
        loaded = sorted(state.get("loaded_skills", {}))
        expected = case["expected_skill"]
        routing = (
            loaded == ([expected] if expected else [])
            if self.variant_skills[variant][0]
            else "n/a"
        )
        called_tools = [
            event["data"].get("name")
            for event in events
            if event["type"] == "tool_call"
        ]
        required_tools_ok = all(name in called_tools for name in case["required_tools"])
        usage = state.get("usage", {})
        return {
            "case_id": case["id"],
            "variant": variant,
            "trial": trial,
            "session_id": session_id,
            "run_id": state["id"],
            "phase": state["phase"],
            "outcome_pass": bool(outcome and required_tools_ok),
            "routing_pass_or_na": routing,
            "input_tokens": usage.get("input_tokens")
            if usage.get("complete")
            else None,
            "output_tokens": usage.get("output_tokens")
            if usage.get("complete")
            else None,
            "usage_complete": bool(usage.get("complete")),
            "skill_activations": loaded,
            "mcp_calls": sum(event["type"] == "mcp_call" for event in events),
            "tool_calls": called_tools,
            "events": str(events_file.relative_to(self.output)),
            "error": error,
        }

    def read_results(self) -> list[dict]:
        if not self.results_file.exists():
            return []
        return [
            json.loads(line)
            for line in self.results_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def write_summary(self, results: list[dict]) -> None:
        summary = summarize(results)
        (self.output / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        lines = ["# Eval summary", ""]
        for case_id, variants in summary["cases"].items():
            lines.append(f"## {case_id}")
            lines.append("")
            for variant, values in variants.items():
                lines.append(
                    f"- {variant}: {values['passed']}/{values['trials']} passed; "
                    f"routing errors: {values['routing_errors']}; "
                    f"average tokens: {values['average_tokens']}; "
                    f"usage complete: {values['usage_complete']}/"
                    f"{values['trials']}; MCP calls: {values['mcp_calls']}; "
                    f"errors: {values['errors']}; tools: {values['tool_calls']}"
                )
            lines.append("")
        lines.extend(["## Trials", ""])
        for item in results:
            lines.append(
                f"- {item['case_id']} {item['variant']}{item['trial']}: "
                f"pass={item['outcome_pass']}; routing="
                f"{item['routing_pass_or_na']}; [events]({item['events']})"
            )
        (self.output / "summary.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )


def check_result(
    checker: str, workspace: Path, state: dict, events: list[dict]
) -> bool:
    if checker == "order_tests":
        test_file = workspace / "test_order.py"
        before = hashlib.sha256(test_file.read_bytes()).hexdigest()
        result = subprocess.run(
            ["python3", "-m", "unittest", "-v"],
            cwd=workspace,
            capture_output=True,
            timeout=10,
            check=False,
        )
        after = hashlib.sha256(test_file.read_bytes()).hexdigest()
        return result.returncode == 0 and before == after
    if checker == "review_report":
        path = workspace / "review.md"
        if not path.is_file():
            return False
        text = path.read_text(encoding="utf-8").lower()
        return all(word in text for word in ("correctness", "maintainability", "tests"))
    if checker == "json_ids":
        path = workspace / "ids.json"
        if not path.is_file():
            return False
        try:
            return set(json.loads(path.read_text(encoding="utf-8"))) == {"T1", "T3"}
        except (json.JSONDecodeError, TypeError):
            return False
    if checker == "missing_data":
        return (
            not (workspace / "summary.json").exists() and state["phase"] != "completed"
        )
    if checker == "mcp_failure":
        failed_mcp = any(
            event["type"] == "mcp_result" and not event["data"].get("ok")
            for event in events
        )
        return failed_mcp and not (workspace / "issue-report.json").exists()
    raise EvalError(f"unknown checker: {checker}")


def summarize(results: list[dict]) -> dict:
    cases: dict[str, dict] = {}
    for item in results:
        values = cases.setdefault(item["case_id"], {}).setdefault(
            item["variant"],
            {
                "trials": 0,
                "passed": 0,
                "routing_errors": 0,
                "usage_complete": 0,
                "mcp_calls": 0,
                "errors": 0,
                "tool_calls": {},
                "tokens": [],
            },
        )
        values["trials"] += 1
        values["passed"] += int(item["outcome_pass"])
        values["routing_errors"] += int(item["routing_pass_or_na"] is False)
        values["usage_complete"] += int(item.get("usage_complete") is True)
        values["mcp_calls"] += int(item.get("mcp_calls", 0))
        values["errors"] += int(bool(item.get("error")))
        for name in item.get("tool_calls", []):
            values["tool_calls"][name] = values["tool_calls"].get(name, 0) + 1
        if isinstance(item.get("input_tokens"), int) and isinstance(
            item.get("output_tokens"), int
        ):
            values["tokens"].append(item["input_tokens"] + item["output_tokens"])
    for variants in cases.values():
        for values in variants.values():
            tokens = values.pop("tokens")
            values["average_tokens"] = (
                round(sum(tokens) / len(tokens), 2) if tokens else "unknown"
            )
    return {"trials": len(results), "cases": cases}
