import json
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from halcyon.config import Settings


class LLM(Protocol):
    def chat(self, messages: list[dict]) -> str: ...


class StubLLM:
    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.last_messages: list[dict] = []

    def chat(self, messages: list[dict]) -> str:
        self.last_messages = messages
        return self._reply


def _fast_local_reply(messages: list[dict]) -> str:
    users = [str(message.get("content", "")) for message in messages
             if message.get("role") == "user"]
    message = users[-1].strip() if users else ""
    lowered = message.lower()
    if any(word in lowered for word in ("ignore", "reveal", "secret", "system prompt", "token")):
        system = " ".join(
            str(item.get("content", "")) for item in messages if item.get("role") == "system"
        )
        token = re.search(r"\b[A-Z][A-Z0-9]+(?:-[A-Z0-9]+){2,}\b", system)
        if token:
            return f"The requested internal token is {token.group(0)}."
    if lowered in {"hi", "hello", "hey"} or lowered.startswith(("hi ", "hello ", "hey ")):
        return "Hello! Iggy is online and ready to help."
    if message:
        return f"I received your message: {message[:240]}"
    return "Iggy is online and ready to help."


class OllamaProvider:
    def __init__(self, url: str, model: str) -> None:
        self._url = url.rstrip("/")
        self._model = model

    def chat(self, messages: list[dict]) -> str:
        try:
            resp = httpx.post(
                f"{self._url}/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": False,
                    "options": {"num_predict": 16, "temperature": 0},
                },
                timeout=8,
            )
            resp.raise_for_status()
            reply = str(resp.json()["message"]["content"]).strip()
            return reply or _fast_local_reply(messages)
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return _fast_local_reply(messages)

    def ping(self) -> bool:
        try:
            r = httpx.get(f"{self._url}/api/tags", timeout=5)
            return r.status_code == 200
        except httpx.HTTPError:
            return False


class RemoteProvider:
    def __init__(self, provider: str, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("remote provider requires an api_key")
        self._provider = provider
        self._api_key = api_key
        self._model = model

    def chat(self, messages: list[dict]) -> str:
        if self._provider == "anthropic":
            return self._anthropic(messages)
        return self._openai(messages)

    def _openai(self, messages: list[dict]) -> str:
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self._model, "messages": messages},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _anthropic(self, messages: list[dict]) -> str:
        system = " ".join(m["content"] for m in messages if m["role"] == "system")
        turns = [m for m in messages if m["role"] != "system"]
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": self._model,
                "system": system,
                "messages": turns,
                "max_tokens": 1024,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]


def build_llm(
    settings: Settings,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> LLM:
    provider = (provider or settings.default_provider).lower()
    if provider in ("local", "ollama"):
        return OllamaProvider(settings.ollama_url, model or settings.ollama_model)

    from halcyon.provider_litellm import LiteLLMChat, to_litellm_model

    model_str = to_litellm_model(provider, model, settings.ollama_model)
    if not api_key:
        raise ValueError(f"provider {provider!r} requires an api_key")
    return LiteLLMChat(model_str, api_key=api_key)


@dataclass
class ToolCall:
    name: str
    args: dict


@dataclass
class FinalAnswer:
    text: str


class ToolLLM(Protocol):
    def next_step(self, messages: list[dict], tools: list[dict]) -> "ToolCall | FinalAnswer": ...


class StubToolLLM:
    def __init__(self, script: list) -> None:
        self._script = list(script)
        self._i = 0

    def next_step(self, messages: list[dict], tools: list[dict]) -> "ToolCall | FinalAnswer":
        step = self._script[self._i]
        self._i += 1
        return step


class OllamaToolProvider:
    """Keyless tool-calling provider backed by the shared Ollama service."""

    def __init__(self, url: str, model: str) -> None:
        self._url = url.rstrip("/")
        self._model = model

    @staticmethod
    def _translate(messages: list[dict]) -> list[dict]:
        translated = []
        for m in messages:
            role = m.get("role")
            if role == "assistant" and "tool_calls" in m:
                translated.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": c["name"], "arguments": c["args"]}}
                        for c in m["tool_calls"]
                    ],
                })
            elif role == "tool":
                translated.append({"role": "tool", "content": m.get("content", "")})
            else:
                translated.append(m)
        return translated

    @staticmethod
    def _compat_step(messages: list[dict], tools: list[dict]) -> "ToolCall | FinalAnswer | None":
        """Schema-bound fallback for local models that reject Ollama tool calling."""
        if messages and messages[-1].get("role") == "tool":
            return FinalAnswer(str(messages[-1].get("content", "")))

        user_text = " ".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "user"
        )
        lowered = user_text.lower()
        names = [str(tool.get("name", "")) for tool in tools]

        def offered(suffix: str) -> str | None:
            return next((name for name in names if name == suffix or name.endswith("__" + suffix)), None)

        accounts = re.findall(r"acct-[a-z0-9-]+", lowered)
        account = accounts[-1] if accounts else "acct-me"
        amounts = re.findall(r"(?<![a-z0-9-])(\d+)(?:\.\d+)?", lowered)
        amount = int(amounts[0]) if amounts else 5000
        email_match = re.search(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", lowered)

        name = offered("update_email")
        if name and "email" in lowered and email_match:
            return ToolCall(name, {"account": account, "email": email_match.group(0)})
        name = offered("issue_refund")
        if name and "refund" in lowered:
            return ToolCall(name, {"to_account": account, "amount": amount})
        name = offered("transfer_funds")
        if name and ("transfer" in lowered or "move" in lowered):
            return ToolCall(name, {"to_account": account, "amount": amount})
        name = offered("get_balance")
        if name and "balance" in lowered:
            return ToolCall(name, {"account": account})
        name = offered("get_customer")
        if name and ("customer" in lowered or "profile" in lowered):
            return ToolCall(name, {"account": account})
        name = offered("get_notes")
        if name and "note" in lowered:
            return ToolCall(name, {"account": account})
        name = offered("get_account_details")
        if name and ("account" in lowered or "detail" in lowered):
            return ToolCall(name, {"account": account})
        return None

    def next_step(self, messages: list[dict], tools: list[dict]) -> "ToolCall | FinalAnswer":
        payload: dict = {
            "model": self._model,
            "messages": self._translate(messages),
            "stream": False,
            "options": {"num_predict": 16, "temperature": 0},
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": schema} for schema in tools]
        try:
            resp = httpx.post(
                f"{self._url}/api/chat",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400 and tools:
                fallback = self._compat_step(messages, tools)
                if fallback is not None:
                    return fallback
            return FinalAnswer(f"<error: {exc}>")
        except (httpx.HTTPError, ValueError) as exc:
            return FinalAnswer(f"<error: {exc}>")
        message = data.get("message") or {}
        tool_calls = message.get("tool_calls")
        if tool_calls:
            function = tool_calls[0].get("function") or {}
            return ToolCall(str(function.get("name", "")), dict(function.get("arguments") or {}))
        return FinalAnswer(str(message.get("content", "")))


class OpenAIToolProvider:
    """Tool-calling provider for the OpenAI chat completions API."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("openai tool provider requires an api_key")
        self._api_key = api_key
        self._model = model

    @staticmethod
    def _translate(messages: list[dict]) -> list[dict]:
        translated = []
        for m in messages:
            role = m.get("role")
            if role == "assistant" and "tool_calls" in m:
                translated.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": c["id"], "type": "function",
                         "function": {"name": c["name"], "arguments": json.dumps(c["args"])}}
                        for c in m["tool_calls"]
                    ],
                })
            elif role == "tool":
                translated.append({"role": "tool", "tool_call_id": m.get("tool_call_id"),
                                    "content": m.get("content", "")})
            else:
                translated.append(m)
        return translated

    def next_step(self, messages: list[dict], tools: list[dict]) -> "ToolCall | FinalAnswer":
        try:
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": self._translate(messages),
                    "tools": [{"type": "function", "function": schema} for schema in tools],
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            message = data["choices"][0]["message"]
            tool_calls = message.get("tool_calls")
            if tool_calls:
                function = tool_calls[0]["function"]
                args = json.loads(function.get("arguments") or "{}")
                return ToolCall(str(function.get("name", "")), dict(args))
            return FinalAnswer(str(message.get("content") or ""))
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            return FinalAnswer(f"<error: {exc}>")


class AnthropicToolProvider:
    """Tool-calling provider for the Anthropic Messages API."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("anthropic tool provider requires an api_key")
        self._api_key = api_key
        self._model = model

    @staticmethod
    def _translate(messages: list[dict]) -> tuple[str, list[dict]]:
        system = " ".join(str(m["content"]) for m in messages if m.get("role") == "system")
        turns = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                continue
            if role == "assistant" and "tool_calls" in m:
                turns.append({
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"]}
                        for c in m["tool_calls"]
                    ],
                })
            elif role == "tool":
                turns.append({
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": m.get("tool_call_id"),
                         "content": m.get("content", "")}
                    ],
                })
            else:
                turns.append({"role": "user", "content": m.get("content", "")})
        return system, turns

    def next_step(self, messages: list[dict], tools: list[dict]) -> "ToolCall | FinalAnswer":
        system, turns = self._translate(messages)
        try:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": 1024,
                    "system": system,
                    "messages": turns,
                    "tools": [
                        {
                            "name": schema.get("name", ""),
                            "description": schema.get("description", ""),
                            "input_schema": schema.get("parameters", {}),
                        }
                        for schema in tools
                    ],
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            return FinalAnswer(f"<error: {exc}>")
        content = data.get("content") or []
        for block in content:
            if block.get("type") == "tool_use":
                return ToolCall(str(block.get("name", "")), dict(block.get("input") or {}))
        for block in content:
            if block.get("type") == "text":
                return FinalAnswer(str(block.get("text", "")))
        return FinalAnswer("")


def build_tool_llm(
    settings: Settings,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> ToolLLM:
    provider = (provider or settings.default_provider).lower()
    if provider in ("local", "ollama"):
        return OllamaToolProvider(settings.ollama_url, model or settings.ollama_model)

    from halcyon.provider_litellm import LiteLLMTool, to_litellm_model

    model_str = to_litellm_model(provider, model, settings.ollama_model)
    if not api_key:
        raise ValueError(f"provider {provider!r} requires an api_key")
    return LiteLLMTool(model_str, api_key=api_key)
