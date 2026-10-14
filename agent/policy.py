import json
import re
import shlex
from pathlib import Path, PureWindowsPath


class PolicyError(ValueError):
    pass


class Policy:
    def __init__(self, workspace: Path, filename: Path) -> None:
        self.root = workspace.resolve(strict=True)
        config_path = filename.resolve(strict=True)
        if config_path.is_relative_to(self.root):
            raise PolicyError("policy must be outside workspace")
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            self.commands = data["commands"]
            self.limits = data["limits"]
            self.allowed = [self._configured(x) for x in data["directories"]["allow"]]
            self.denied = [self._configured(x) for x in data["directories"]["deny"]]
            self.protected = [self._configured(x) for x in data["protected_files"]]
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise PolicyError("invalid policy file") from error
        if not self.allowed:
            raise PolicyError("at least one allowed directory is required")
        for key in (
            "model_requests",
            "tool_calls",
            "side_effects",
            "tool_output_bytes",
            "single_result_bytes",
            "bash_seconds",
            "file_bytes",
        ):
            if not isinstance(self.limits.get(key), int) or self.limits[key] <= 0:
                raise PolicyError(f"invalid limit: {key}")

    def _configured(self, value: str) -> Path:
        if not isinstance(value, str) or not value:
            raise PolicyError("configured path must be a string")
        path = Path(value)
        if path.is_absolute() or PureWindowsPath(value).drive or ".." in path.parts:
            raise PolicyError("configured path must be relative")
        result = (self.root / path).resolve(strict=False)
        if not result.is_relative_to(self.root):
            raise PolicyError("configured path escapes workspace")
        return result

    def path(self, value: str, *, change: bool = False) -> Path:
        if not isinstance(value, str) or not value:
            raise PolicyError("path must be a nonempty string")
        path = Path(value)
        if path.is_absolute() or PureWindowsPath(value).drive or ".." in path.parts:
            raise PolicyError("absolute paths and '..' are forbidden")
        result = (self.root / path).resolve(strict=False)
        if not result.is_relative_to(self.root):
            raise PolicyError("path escapes workspace through a symlink")
        if not any(result.is_relative_to(item) for item in self.allowed):
            raise PolicyError("path is outside allowed directories")
        if any(result.is_relative_to(item) for item in self.denied):
            raise PolicyError("path is denied")
        if change and result in self.protected:
            raise PolicyError("file is protected")
        return result

    def bash(self, command: str, cwd: str) -> Path:
        directory = self.path(cwd)
        if not directory.is_dir():
            raise PolicyError("Bash cwd must be a directory")
        if not isinstance(command, str) or not command:
            raise PolicyError("command must be a nonempty string")
        if re.search(r"[|&;<>()$`\\\n\r]", command):
            raise PolicyError("complex shell syntax is forbidden")
        try:
            words = shlex.split(command)
        except ValueError as error:
            raise PolicyError("invalid command syntax") from error
        if not words or words[0] in {"bash", "sh", "zsh"}:
            raise PolicyError("nested shells are forbidden")
        if any("/" in word or "\\" in word or word == ".." for word in words):
            raise PolicyError("paths in Bash arguments are forbidden")
        if command in self.commands["deny"]:
            raise PolicyError("command is denied")
        if command not in self.commands["allow"]:
            raise PolicyError("command is not allowed")
        return directory

    def check(self, name: str, arguments: dict, *, planning: bool) -> None:
        if planning and name not in {"list_files", "read_file"}:
            raise PolicyError("Plan Mode permits reading only")
        if name == "Bash":
            self.bash(arguments["command"], arguments["cwd"])
        else:
            self.path(
                arguments["path"],
                change=name in {"write_file", "delete_file"},
            )

    def needs_approval(self, name: str, mode: str) -> bool:
        return name == "delete_file" or (
            mode == "safe" and name in {"write_file", "Bash"}
        )
