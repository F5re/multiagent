import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from agent.evals import CHECKER_VERSION, EvalRunner
from agent.market import Market
from agent.model import ChatModel
from agent.skills import SkillRegistry


class UpdateError(RuntimeError):
    pass


class SkillUpdater:
    token_growth_limit = 0.20

    def __init__(
        self,
        root: Path,
        market_config: Path,
        skills_dir: Path | None = None,
        state_dir: Path | None = None,
    ) -> None:
        self.root = root
        self.skills_dir = skills_dir or root / "skills"
        self.state_dir = state_dir or root / ".agent_state" / "updates"
        self.market = Market(
            market_config, self.skills_dir, self.state_dir.parent / "market"
        )

    def evaluate(self, name: str, trials: int = 3, fresh: bool = False) -> dict:
        if trials != 3:
            raise UpdateError(
                "update evaluation requires three trials per case and version"
            )
        if not self.market.installed(name):
            raise UpdateError("skill must be installed before update evaluation")
        self.market.stage(name)
        candidate = self.market.candidate(name)
        comparison = self.state_dir / "comparisons" / name
        saved = comparison / "results.jsonl"
        if comparison.exists() and fresh:
            archive = self.state_dir / "archive" / name / uuid.uuid4().hex
            archive.parent.mkdir(parents=True, exist_ok=True)
            os.replace(comparison, archive)
        elif saved.is_file():
            versions = {
                json.loads(line).get("checker_version")
                for line in saved.read_text(encoding="utf-8").splitlines()
                if line.strip()
            }
            if versions != {CHECKER_VERSION}:
                archive = self.state_dir / "archive" / name / uuid.uuid4().hex
                archive.parent.mkdir(parents=True, exist_ok=True)
                os.replace(comparison, archive)
        old_skills = comparison / "configurations" / "old"
        new_skills = comparison / "configurations" / "new"
        for directory in (old_skills, new_skills):
            if directory.exists():
                shutil.rmtree(directory)
            shutil.copytree(self.skills_dir, directory)
        shutil.rmtree(new_skills / name)
        shutil.copytree(candidate, new_skills / name)
        runner = EvalRunner(
            self.root,
            self.root / "evals" / "cases.json",
            comparison,
            model_factory=ChatModel,
            variant_skills={"old": (True, old_skills), "new": (True, new_skills)},
        )
        results = runner.run(trials)
        decision = self.decide(results)
        decision.update(
            {
                "skill": name,
                "old_version": SkillRegistry(self.skills_dir).load(name).version,
                "new_version": SkillRegistry._read(
                    candidate / "SKILL.md", False
                ).version,
                "candidate_revision": self.market.catalog[name]["revision"],
                "trials": len(results),
            }
        )
        comparison.mkdir(parents=True, exist_ok=True)
        decision_file = comparison / "decision.json"
        decision["action"] = "ready" if decision["accepted"] else "rejected"
        decision_file.write_text(
            json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if decision["accepted"]:
            self.apply(name)
            decision["action"] = "applied"
        decision_file.write_text(
            json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._log("update_decision", decision)
        return decision

    def decide(self, results: list[dict]) -> dict:
        reasons = []
        grouped: dict[str, dict[str, list[dict]]] = {}
        for item in results:
            grouped.setdefault(item["case_id"], {}).setdefault(
                item["variant"], []
            ).append(item)
        expected_cases = {
            "fix-failing-test",
            "python-review",
            "no-matching-skill",
            "missing-data",
            "mcp-failure",
        }
        if set(grouped) != expected_cases or any(
            len(variants.get(variant, [])) != 3
            for variants in grouped.values()
            for variant in ("old", "new")
        ):
            reasons.append(
                "comparison requires five cases and three trials per version"
            )
        for case_id, variants in grouped.items():
            old_pass = sum(item["outcome_pass"] for item in variants.get("old", []))
            new_pass = sum(item["outcome_pass"] for item in variants.get("new", []))
            if new_pass < old_pass:
                reasons.append(
                    f"success rate decreased for {case_id}: {old_pass} to {new_pass}"
                )
        new_results = [item for item in results if item["variant"] == "new"]
        if not new_results or any(
            item["routing_pass_or_na"] is not True for item in new_results
        ):
            reasons.append("candidate skill routing did not pass every scenario")
        protected = {"missing-data", "mcp-failure"}
        if any(
            not item["outcome_pass"]
            for item in new_results
            if item["case_id"] in protected
        ):
            reasons.append("candidate failed a required limitation scenario")
        if not results or any(not item.get("usage_complete") for item in results):
            reasons.append("token usage is incomplete")
            token_growth = None
        else:
            old_tokens = average_tokens(
                [item for item in results if item["variant"] == "old"]
            )
            new_tokens = average_tokens(new_results)
            token_growth = (new_tokens - old_tokens) / old_tokens if old_tokens else 0.0
            if token_growth > self.token_growth_limit:
                reasons.append(
                    f"average token growth {token_growth:.1%} exceeds "
                    f"{self.token_growth_limit:.0%}"
                )
        return {
            "accepted": not reasons,
            "reasons": reasons or ["all predefined update checks passed"],
            "token_growth": token_growth,
            "token_growth_limit": self.token_growth_limit,
        }

    def apply(self, name: str) -> dict:
        current = SkillRegistry(self.skills_dir).load(name)
        candidate = self.market.candidate(name)
        updated = SkillRegistry._read(candidate / "SKILL.md", False)
        decision_file = self.state_dir / "comparisons" / name / "decision.json"
        if not decision_file.is_file():
            raise UpdateError("accepted eval decision is required before apply")
        decision = json.loads(decision_file.read_text(encoding="utf-8"))
        if not (
            decision.get("accepted") is True
            and decision.get("action") == "ready"
            and decision.get("old_version") == current.version
            and decision.get("new_version") == updated.version
            and decision.get("candidate_revision")
            == self.market.catalog[name]["revision"]
            and decision.get("trials") == 30
        ):
            raise UpdateError("candidate has no matching accepted eval decision")
        if current.version == updated.version:
            raise UpdateError("candidate version is already active")
        backup = self.state_dir / "backups" / name / current.version
        backup.parent.mkdir(parents=True, exist_ok=True)
        if backup.exists():
            shutil.rmtree(backup)
        temporary_root = Path(
            tempfile.mkdtemp(prefix=".update-", dir=self.skills_dir.parent)
        )
        temporary = temporary_root / name
        shutil.copytree(candidate, temporary)
        if SkillRegistry(temporary_root).errors:
            shutil.rmtree(temporary_root)
            raise UpdateError("candidate validation failed")
        active = self.skills_dir / name
        try:
            os.replace(active, backup)
            try:
                os.replace(temporary, active)
            except Exception:
                os.replace(backup, active)
                raise
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)
        result = {
            "name": name,
            "old_version": current.version,
            "new_version": updated.version,
            "backup": str(backup),
        }
        self._log("update_applied", result)
        return result

    def rollback(self, name: str) -> dict:
        backups = self.state_dir / "backups" / name
        candidates = (
            sorted(
                (item for item in backups.iterdir() if item.is_dir()),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            if backups.is_dir()
            else []
        )
        if not candidates:
            raise UpdateError("no rollback version is available")
        active = self.skills_dir / name
        current = SkillRegistry(self.skills_dir).load(name)
        previous = SkillRegistry._read(candidates[0] / "SKILL.md", False)
        removed = self.state_dir / "rolled_back" / name / current.version
        removed.parent.mkdir(parents=True, exist_ok=True)
        if removed.exists():
            shutil.rmtree(removed)
        os.replace(active, removed)
        try:
            os.replace(candidates[0], active)
        except Exception:
            os.replace(removed, active)
            raise
        result = {
            "name": name,
            "from_version": current.version,
            "to_version": previous.version,
        }
        self._log("update_rolled_back", result)
        return result

    def status(self, name: str) -> dict:
        active = SkillRegistry(self.skills_dir).load(name)
        candidate = self.market.candidate(name)
        candidate_version = (
            SkillRegistry._read(candidate / "SKILL.md", False).version
            if candidate.is_dir()
            else None
        )
        decision = self.state_dir / "comparisons" / name / "decision.json"
        return {
            "name": name,
            "active_version": active.version,
            "candidate_version": candidate_version,
            "decision": (
                json.loads(decision.read_text(encoding="utf-8"))
                if decision.is_file()
                else None
            ),
        }

    def _log(self, event_type: str, data: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        event = {
            "id": uuid.uuid4().hex,
            "time": datetime.now().astimezone().isoformat(),
            "type": event_type,
            "data": data,
        }
        with (self.state_dir / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")


def average_tokens(results: list[dict]) -> float:
    if not results:
        return 0.0
    return sum(item["input_tokens"] + item["output_tokens"] for item in results) / len(
        results
    )
