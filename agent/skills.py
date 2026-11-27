from dataclasses import dataclass
from pathlib import Path


class SkillError(ValueError):
    pass


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    version: str
    path: Path
    content: str


class SkillRegistry:
    def __init__(self, root: Path, enabled: bool = True) -> None:
        self.root = root
        self.enabled = enabled
        self.skills: dict[str, Skill] = {}
        self.errors: list[dict[str, str]] = []
        if enabled:
            self._discover()

    def _discover(self) -> None:
        if not self.root.exists():
            return
        for filename in sorted(self.root.glob("*/SKILL.md")):
            try:
                skill = self._read(filename)
                if skill.name in self.skills:
                    raise SkillError(f"duplicate skill name: {skill.name}")
                self.skills[skill.name] = skill
            except (OSError, SkillError) as error:
                self.errors.append({"path": str(filename), "error": str(error)})

    @staticmethod
    def _read(filename: Path, require_directory_name: bool = True) -> Skill:
        content = filename.read_text(encoding="utf-8")
        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            raise SkillError("SKILL.md must start with YAML frontmatter")
        try:
            end = next(
                index for index, line in enumerate(lines[1:], 1) if line == "---"
            )
        except StopIteration as error:
            raise SkillError("SKILL.md frontmatter is not closed") from error
        fields: dict[str, str] = {}
        index = 1
        while index < end:
            line = lines[index]
            if ":" not in line:
                raise SkillError(f"invalid frontmatter line: {line}")
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value in {">", ">-", "|", "|-"}:
                parts = []
                index += 1
                while index < end and (
                    lines[index].startswith(" ") or not lines[index].strip()
                ):
                    if lines[index].strip():
                        parts.append(lines[index].strip())
                    index += 1
                fields[key] = " ".join(parts)
                continue
            fields[key] = value.strip("\"'")
            index += 1
        name = fields.get("name", "")
        description = fields.get("description", "")
        version = fields.get("version", "1.0.0")
        if not name or not description:
            raise SkillError("skill name and description are required")
        if require_directory_name and filename.parent.name != name:
            raise SkillError("skill name must match its directory")
        body = "\n".join(lines[end + 1 :]).strip()
        if not body:
            raise SkillError("skill instructions are empty")
        return Skill(name, description, version, filename, content)

    def catalog(self) -> list[dict[str, str]]:
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "version": skill.version,
            }
            for skill in self.skills.values()
        ]

    def load(self, name: str) -> Skill:
        try:
            return self.skills[name]
        except KeyError as error:
            raise SkillError(f"unknown skill: {name}") from error
