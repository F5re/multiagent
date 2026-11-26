import json
import subprocess
import sys
from pathlib import Path


class MCPError(RuntimeError):
    pass


class MCPClient:
    def __init__(self, filename: Path | None) -> None:
        self.filename = filename
        self.servers: dict[str, dict] = {}
        self._tools: dict[str, dict] = {}
        if filename and filename.exists():
            self._load(filename)

    def _load(self, filename: Path) -> None:
        try:
            data = json.loads(filename.read_text(encoding="utf-8"))
            servers = data["servers"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise MCPError("invalid MCP configuration") from error
        if not isinstance(servers, dict):
            raise MCPError("MCP servers must be an object")
        for name, config in servers.items():
            if not isinstance(name, str) or not isinstance(config, dict):
                raise MCPError("invalid MCP server entry")
            command = config.get("command")
            timeout = config.get("timeout_seconds", 5)
            if (
                not isinstance(command, list)
                or not command
                or not all(isinstance(item, str) for item in command)
                or not isinstance(timeout, (int, float))
                or timeout <= 0
            ):
                raise MCPError(f"invalid MCP server configuration: {name}")
            self.servers[name] = config
            for tool in self._exchange(name, "tools/list", {}):
                remote_name = tool.get("name")
                schema = tool.get("inputSchema")
                if not isinstance(remote_name, str) or not isinstance(schema, dict):
                    raise MCPError(f"server {name} returned an invalid tool")
                public_name = f"mcp__{name}__{remote_name}"
                self._tools[public_name] = {
                    "server": name,
                    "remote_name": remote_name,
                    "description": str(tool.get("description", "")),
                    "inputSchema": schema,
                    "read_only": bool(tool.get("annotations", {}).get("readOnlyHint")),
                }

    def definitions(
        self, planning: bool, permitted: set[str] | None = None
    ) -> list[dict]:
        result = []
        for name, tool in self._tools.items():
            if planning and not tool["read_only"]:
                continue
            if permitted is not None and name not in permitted:
                continue
            result.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool["description"],
                        "parameters": tool["inputSchema"],
                    },
                }
            )
        return result

    def names(self) -> set[str]:
        return set(self._tools)

    def validate(self, name: str, arguments: object) -> None:
        if name not in self._tools:
            raise ValueError(f"unknown MCP tool: {name}")
        if not isinstance(arguments, dict):
            raise ValueError("MCP tool arguments must be an object")
        schema = self._tools[name]["inputSchema"]
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list):
            raise ValueError("invalid MCP tool schema")
        if any(key not in arguments for key in required):
            raise ValueError("MCP tool is missing required arguments")
        if schema.get("additionalProperties") is False and any(
            key not in properties for key in arguments
        ):
            raise ValueError("MCP tool received unknown arguments")
        for key, value in arguments.items():
            expected = properties.get(key, {}).get("type")
            if expected == "string" and not isinstance(value, str):
                raise ValueError(f"MCP argument {key} must be a string")

    def call(self, name: str, arguments: dict) -> dict:
        self.validate(name, arguments)
        tool = self._tools[name]
        result = self._exchange(
            tool["server"],
            "tools/call",
            {"name": tool["remote_name"], "arguments": arguments},
        )
        if not isinstance(result, dict):
            raise MCPError("MCP tool returned an invalid result")
        return result

    def details(self, name: str) -> tuple[str, str]:
        tool = self._tools[name]
        return tool["server"], tool["remote_name"]

    def _exchange(self, server: str, method: str, params: dict):
        config = self.servers[server]
        command = [
            sys.executable if item == "{python}" else item for item in config["command"]
        ]
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "coding-agent", "version": "0.2.0"},
                },
            },
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
            {"jsonrpc": "2.0", "id": 2, "method": method, "params": params},
        ]
        payload = "".join(json.dumps(item) + "\n" for item in requests)
        try:
            process = subprocess.run(
                command,
                input=payload,
                text=True,
                capture_output=True,
                timeout=float(config.get("timeout_seconds", 5)),
                cwd=self.filename.parent.parent if self.filename else None,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise MCPError(f"MCP server {server} timed out") from error
        except OSError as error:
            raise MCPError(f"MCP server {server} could not start") from error
        if process.returncode != 0:
            message = process.stderr.strip() or f"exit code {process.returncode}"
            raise MCPError(f"MCP server {server} failed: {message}")
        responses = []
        for line in process.stdout.splitlines():
            try:
                message = json.loads(line)
            except json.JSONDecodeError as error:
                raise MCPError(f"MCP server {server} returned invalid JSON") from error
            if "id" in message:
                responses.append(message)
        response = next((item for item in responses if item.get("id") == 2), None)
        if not response:
            raise MCPError(f"MCP server {server} did not answer {method}")
        if "error" in response:
            raise MCPError(str(response["error"].get("message", "MCP error")))
        result = response.get("result")
        if method == "tools/list":
            if not isinstance(result, dict) or not isinstance(
                result.get("tools"), list
            ):
                raise MCPError(f"MCP server {server} returned invalid tools/list")
            return result["tools"]
        return result
