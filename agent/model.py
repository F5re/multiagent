import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

PLAN_FORMAT = {
    "type": "object",
    "properties": {
        "goal": {"type": "string"},
        "steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "description": {"type": "string"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                    "tools": {
                        "type": "array",
                        "items": {
                            "enum": [
                                "Bash",
                                "list_files",
                                "read_file",
                                "write_file",
                                "delete_file",
                            ]
                        },
                    },
                    "verification": {
                        "type": "object",
                        "properties": {
                            "kind": {
                                "enum": [
                                    "read_files",
                                    "file_changed",
                                    "file_deleted",
                                    "tests_pass",
                                ]
                            },
                            "paths": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "path": {"type": "string"},
                            "command": {"type": "string"},
                        },
                        "required": ["kind"],
                        "additionalProperties": False,
                    },
                },
                "required": [
                    "id",
                    "description",
                    "depends_on",
                    "tools",
                    "verification",
                ],
                "additionalProperties": False,
            },
        },
        "risks": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "done_when": {"type": "string"},
    },
    "required": ["goal", "steps", "risks", "assumptions", "done_when"],
    "additionalProperties": False,
}


def text_tool_calls(content: str, scope: str = "") -> list[dict]:
    text = content.strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    values = []
    decoder = json.JSONDecoder()
    position = 0
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        try:
            value, end = decoder.raw_decode(text, position)
        except json.JSONDecodeError:
            position = text.find("{", position + 1)
            if position < 0:
                break
            continue
        values.append(value)
        position = end
    raw_calls = []
    for value in values:
        if not isinstance(value, dict):
            continue
        if set(value) == {"tool_calls"} and isinstance(value["tool_calls"], list):
            raw_calls.extend(value["tool_calls"])
        elif set(value) == {"name", "arguments"}:
            raw_calls.append(value)
        elif isinstance(value.get("tool_call") or value.get("tool"), str):
            field = "tool_call" if "tool_call" in value else "tool"
            raw_calls.append(
                {
                    "name": value[field],
                    "arguments": {
                        key: item for key, item in value.items() if key != field
                    },
                }
            )
    result = []
    for index, raw in enumerate(raw_calls):
        if not isinstance(raw, dict):
            return []
        if set(raw) == {"function", "arguments"}:
            name = raw["function"]
        elif set(raw) == {"name", "arguments"}:
            name = raw["name"]
        else:
            return []
        arguments = raw["arguments"]
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return []
        packed = json.dumps(
            {"name": name, "arguments": arguments},
            ensure_ascii=False,
            sort_keys=True,
        )
        call_id = hashlib.sha256(f"{scope}:{index}:{packed}".encode()).hexdigest()[:16]
        result.append(
            {
                "id": "text_" + call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        )
    return result


class ModelError(RuntimeError):
    pass


class ChatModel:
    def __init__(self) -> None:
        self.url = os.environ.get("OPENAI_BASE_URL", "").rstrip("/")
        self.key = os.environ.get("OPENAI_API_KEY", "")
        self.name = os.environ.get("OPENAI_MODEL", "")
        try:
            self.timeout = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "300"))
        except ValueError as error:
            raise ModelError("OPENAI_TIMEOUT_SECONDS must be a number") from error
        if not self.url or not self.key or not self.name:
            raise ModelError("OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL required")
        address = urllib.parse.urlsplit(self.url)
        self.ollama_url = None
        if self.key == "ollama" and address.hostname in {"127.0.0.1", "localhost"}:
            self.ollama_url = f"{address.scheme}://{address.netloc}/api/chat"

    def complete(
        self, messages: list[dict], tools: list[dict], json_mode: bool = False
    ) -> dict:
        api_messages = json.loads(json.dumps(messages))
        if self.ollama_url:
            call_names = {}
            for message in api_messages:
                for call in message.get("tool_calls", []):
                    call_names[call["id"]] = call["function"]["name"]
                    arguments = call["function"].get("arguments")
                    if isinstance(arguments, str):
                        call["function"]["arguments"] = json.loads(arguments)
                if message.get("role") == "tool":
                    call_id = message.pop("tool_call_id", "")
                    message["tool_name"] = call_names.get(call_id, "")
        data = {
            "model": self.name,
            "messages": api_messages,
            "tools": tools,
            "stream": False,
        }
        if self.ollama_url:
            data["options"] = {"num_predict": 1200}
            if self.name.startswith("qwen3"):
                data["think"] = False
            if json_mode:
                data["format"] = PLAN_FORMAT
        else:
            data["max_tokens"] = 1200
            if json_mode:
                data["response_format"] = {"type": "json_object"}
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.ollama_url or self.url + "/chat/completions",
            data=body,
            headers={
                "Authorization": "Bearer " + self.key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            raise ModelError(f"Model API returned HTTP {error.code}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise ModelError("Could not reach the model API") from error
        try:
            answer = (
                payload["message"]
                if self.ollama_url
                else payload["choices"][0]["message"]
            )
        except (KeyError, IndexError, TypeError) as error:
            raise ModelError("Model API returned an invalid response") from error
        if not isinstance(answer, dict):
            raise ModelError("Model message must be an object")
        if self.ollama_url:
            content = answer.get("content")
            if isinstance(content, str) and "</think>" in content:
                answer["content"] = content.rsplit("</think>", 1)[1].strip()
                content = answer["content"]
            for call in answer.get("tool_calls", []):
                function = call.get("function", {})
                arguments = function.get("arguments")
                if isinstance(arguments, dict):
                    function["arguments"] = json.dumps(arguments, ensure_ascii=False)
            if (
                not json_mode
                and not answer.get("tool_calls")
                and isinstance(content, str)
            ):
                scope = next(
                    (
                        f"{index}:{message['content']}"
                        for index, message in reversed(list(enumerate(messages)))
                        if message.get("role") == "user"
                        and str(message.get("content", "")).startswith("Current task ")
                    ),
                    "execution",
                )
                calls = text_tool_calls(content, scope)
                allowed = {tool["function"]["name"] for tool in tools}
                calls = [call for call in calls if call["function"]["name"] in allowed]
                if calls:
                    answer["content"] = ""
                    answer["tool_calls"] = calls
        return answer


class FakeModel:
    def __init__(self, answers: list[dict]) -> None:
        self.answers = iter(answers)
        self.requests: list[tuple[list[dict], list[dict]]] = []

    def complete(
        self, messages: list[dict], tools: list[dict], json_mode: bool = False
    ) -> dict:
        self.requests.append((list(messages), list(tools)))
        return next(self.answers)
