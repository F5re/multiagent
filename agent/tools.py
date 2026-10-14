import hashlib
import os
import selectors
import signal
import subprocess
import tempfile
import time
from contextlib import suppress
from pathlib import Path

from agent.policy import Policy, PolicyError

SCHEMAS = {
    "list_files": {"path": str},
    "read_file": {"path": str},
    "write_file": {"path": str, "content": str},
    "delete_file": {"path": str},
    "Bash": {"command": str, "cwd": str},
}
SIDE_EFFECTS = {"write_file", "delete_file", "Bash"}


def definitions(planning: bool, permitted: set[str] | None = None) -> list[dict]:
    names = {"list_files", "read_file"} if planning else set(SCHEMAS)
    if permitted is not None:
        names &= permitted
    descriptions = {
        "list_files": "List files inside a workspace directory.",
        "read_file": "Read one UTF-8 workspace file.",
        "write_file": "Atomically replace one UTF-8 workspace file.",
        "delete_file": "Delete one workspace file.",
        "Bash": "Run one exact allowlisted command in a workspace directory.",
    }
    result = []
    for name in SCHEMAS:
        if name not in names:
            continue
        result.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": descriptions[name],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            key: {"type": "string"} for key in SCHEMAS[name]
                        },
                        "required": list(SCHEMAS[name]),
                        "additionalProperties": False,
                    },
                },
            }
        )
    return result


def validate(name: str, arguments: object) -> None:
    if name not in SCHEMAS:
        raise ValueError(f"unknown tool: {name}")
    expected = SCHEMAS[name]
    if not isinstance(arguments, dict) or set(arguments) != set(expected):
        raise ValueError(f"{name} requires exactly: {', '.join(expected)}")
    for key in expected:
        if not isinstance(arguments[key], str):
            raise ValueError(f"{name}.{key} must be a string")


def file_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(policy: Policy, name: str, arguments: dict, output_limit: int) -> dict:
    validate(name, arguments)
    policy.check(name, arguments, planning=False)
    if name == "Bash":
        return _run_bash(policy, arguments, output_limit)
    target = policy.path(
        arguments["path"], change=name in {"write_file", "delete_file"}
    )
    if name == "list_files":
        if not target.is_dir():
            raise ValueError("path is not a directory")
        return {"files": _list_files(policy, target)}
    if name == "read_file":
        if not target.is_file():
            raise ValueError("path is not a file")
        if target.stat().st_size > policy.limits["file_bytes"]:
            raise ValueError("file is too large")
        raw = target.read_bytes()
        return {"path": arguments["path"], "content": raw.decode("utf-8")}
    if name == "write_file":
        return _write(policy, target, arguments)
    if name == "delete_file":
        if not target.is_file():
            raise ValueError("path is not a file")
        target.unlink()
        return {"path": arguments["path"], "deleted": True}
    raise AssertionError(name)


def _write(policy: Policy, target: Path, arguments: dict) -> dict:
    if not target.parent.is_dir():
        raise ValueError("parent directory does not exist")
    content = arguments["content"].encode("utf-8")
    if len(content) > policy.limits["file_bytes"]:
        raise ValueError("content is too large")
    before = file_hash(target)
    descriptor, temporary_name = tempfile.mkstemp(dir=target.parent, prefix=".agent-")
    try:
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target)
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return {
        "path": arguments["path"],
        "bytes_written": len(content),
        "before_sha256": before,
        "after_sha256": hashlib.sha256(content).hexdigest(),
    }


def _list_files(policy: Policy, target: Path) -> list[str]:
    files = []
    for directory, names, filenames in os.walk(target, followlinks=False):
        current = Path(directory)
        allowed_names = []
        for name in names:
            candidate = current / name
            relative = candidate.relative_to(policy.root).as_posix()
            try:
                policy.path(relative)
            except PolicyError:
                continue
            if not candidate.is_symlink():
                allowed_names.append(name)
        names[:] = allowed_names
        for name in filenames:
            candidate = current / name
            if candidate.is_symlink():
                continue
            relative = candidate.relative_to(policy.root).as_posix()
            try:
                allowed = policy.path(relative)
            except PolicyError:
                continue
            if allowed.is_file():
                files.append(relative)
    return sorted(files)


def _run_bash(policy: Policy, arguments: dict, output_limit: int) -> dict:
    directory = policy.bash(arguments["command"], arguments["cwd"])
    process = subprocess.Popen(
        ["/bin/bash", "--noprofile", "--norc", "-c", arguments["command"]],
        cwd=directory,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("Bash output pipes are unavailable")
    streams = selectors.DefaultSelector()
    streams.register(process.stdout, selectors.EVENT_READ, "stdout")
    streams.register(process.stderr, selectors.EVENT_READ, "stderr")
    output = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + policy.limits["bash_seconds"]
    timed_out = False
    truncated = False
    try:
        while streams.get_map() or process.poll() is None:
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0 and process.poll() is None:
                timed_out = True
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except PermissionError:
                    with suppress(ProcessLookupError):
                        process.kill()
                except ProcessLookupError:
                    pass
            events = streams.select(max(0, min(0.1, remaining_time)))
            for key, _ in events:
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    streams.unregister(key.fileobj)
                    continue
                kept = sum(len(value) for value in output.values())
                available = max(0, output_limit - kept)
                output[key.data].extend(chunk[:available])
                if len(chunk) > available:
                    truncated = True
        process.wait()
    finally:
        streams.close()
    return {
        "stdout": output["stdout"].decode("utf-8", errors="replace"),
        "stderr": output["stderr"].decode("utf-8", errors="replace"),
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "truncated": truncated,
    }
