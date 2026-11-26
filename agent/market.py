import hashlib
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from agent.skills import SkillRegistry


class MarketError(RuntimeError):
    pass


class Market:
    def __init__(
        self, config_file: Path | None, skills_dir: Path, state_dir: Path
    ) -> None:
        self.config_file = config_file
        self.skills_dir = skills_dir
        self.state_dir = state_dir
        self.config: dict = {}
        self.catalog: dict[str, dict] = {}
        if config_file and config_file.exists():
            self._load()

    def _load(self) -> None:
        if self.config_file is None:
            raise MarketError("market configuration is missing")
        try:
            self.config = json.loads(self.config_file.read_text(encoding="utf-8"))
            source = self.config["source"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise MarketError("invalid market configuration") from error
        source_path = Path(source)
        if source_path.is_absolute() or ".." in source_path.parts:
            raise MarketError("market source must be a safe relative path")
        root = self.config_file.parent.parent
        catalog_file = (root / source_path).resolve()
        if not catalog_file.is_relative_to(root.resolve()):
            raise MarketError("market source escapes the project")
        try:
            data = json.loads(catalog_file.read_text(encoding="utf-8"))
            entries = data["skills"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise MarketError("market catalog is unavailable or invalid") from error
        if not isinstance(entries, list):
            raise MarketError("market skills must be an array")
        for entry in entries:
            if not isinstance(entry, dict) or not {
                "name",
                "version",
                "path",
                "description",
            } <= set(entry):
                raise MarketError("market entry is invalid")
            package = (catalog_file.parent / entry["path"]).resolve()
            if not package.is_relative_to(catalog_file.parent.resolve()):
                raise MarketError("market package escapes its source")
            item = dict(entry)
            item["package"] = str(package)
            item["revision"] = package_hash(package)
            self.catalog[item["name"]] = item

    def available(self) -> bool:
        return bool(self.catalog)

    def search(self, query: str) -> list[dict]:
        words = query.lower().split()
        installed = SkillRegistry(self.skills_dir).skills
        return [
            public_entry(item)
            for item in self.catalog.values()
            if item["name"] not in installed
            and all(
                word in f"{item['name']} {item['description']}".lower()
                for word in words
            )
        ]

    def check(self) -> dict:
        installed = SkillRegistry(self.skills_dir).skills
        new = []
        updates = []
        staged = []
        for name, item in self.catalog.items():
            current = installed.get(name)
            if current is None:
                new.append(public_entry(item))
            elif current.version != item["version"]:
                updates.append(
                    {
                        **public_entry(item),
                        "old_version": current.version,
                    }
                )
                if self.config.get("auto_update", False) and self.stage(name):
                    staged.append(name)
        result = {
            "checked_at": datetime.now().astimezone().isoformat(),
            "new": new,
            "updates": updates,
            "staged": staged,
            "auto_update": bool(self.config.get("auto_update", False)),
        }
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / "last_check.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._log("market_check", result)
        return result

    def install(self, name: str) -> dict:
        try:
            if (self.skills_dir / name).exists():
                raise MarketError("skill is already installed")
            item = self._entry(name)
            self._validated_copy(Path(item["package"]), self.skills_dir / name)
            result = {**public_entry(item), "installed": True}
            self._log("market_install", result)
            return result
        except MarketError as error:
            self._log("market_error", {"name": name, "message": str(error)})
            raise

    def stage(self, name: str) -> bool:
        item = self._entry(name)
        target = self.state_dir / "candidates" / name / item["version"]
        marker = target / ".revision"
        if marker.is_file() and marker.read_text(encoding="utf-8") == item["revision"]:
            return False
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._validated_copy(Path(item["package"]), target)
        marker.write_text(item["revision"], encoding="utf-8")
        self._log(
            "market_candidate_staged",
            {"name": name, "version": item["version"], "revision": item["revision"]},
        )
        return True

    def installed(self, name: str) -> bool:
        return name in SkillRegistry(self.skills_dir).skills

    def candidate(self, name: str) -> Path:
        item = self._entry(name)
        return self.state_dir / "candidates" / name / item["version"]

    def _entry(self, name: str) -> dict:
        try:
            return self.catalog[name]
        except KeyError as error:
            raise MarketError(f"skill is absent from market: {name}") from error

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

    @staticmethod
    def _validated_copy(source: Path, target: Path) -> None:
        if not source.is_dir():
            raise MarketError("market package directory is missing")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".skill-", dir=target.parent))
        try:
            shutil.copytree(source, temporary / source.name)
            copied = temporary / source.name
            registry = SkillRegistry(copied.parent)
            if registry.errors or copied.name not in registry.skills:
                message = (
                    registry.errors[0]["error"] if registry.errors else "invalid skill"
                )
                raise MarketError(message)
            os.replace(copied, target)
        finally:
            shutil.rmtree(temporary, ignore_errors=True)


def package_hash(path: Path) -> str:
    if not path.is_dir():
        raise MarketError("market package is missing")
    digest = hashlib.sha256()
    for filename in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(filename.relative_to(path).as_posix().encode())
        digest.update(filename.read_bytes())
    return digest.hexdigest()


def public_entry(item: dict) -> dict:
    return {key: item[key] for key in ("name", "version", "description", "revision")}
