"""Provider-agnostic language-model interface for the AI Analyst.

The Analyst talks to a `Provider`, never to a vendor directly. A provider takes a system prompt, a list of messages and the tool specifications, and
returns text and/or tool calls. Messages use one canonical, Anthropic-style shape (`{"role", "content"}` where content is text or a list of
`text` / `tool_use` / `tool_result` blocks); another vendor is added by writing an adapter that translates to and from it.

Credentials are read from the server environment only (ANTHROPIC_API_KEY) and are never returned, logged or placed in a prompt. Every failure,
whatever its cause, becomes a `ProviderError` with a generic message: provider response bodies and keys never reach a caller.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol


class ProviderError(RuntimeError):
    """Any provider failure. The message is generic by design."""


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class ProviderReply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    stop_reason: str | None = None
    # the assistant turn exactly as it should be sent back to the provider on the next request
    message: dict | None = None


class Provider(Protocol):
    name: str
    model: str

    def chat(self, system: str, messages: list[dict], tools: list[dict], max_tokens: int, timeout: float) -> ProviderReply: ...


class AnthropicProvider:
    """Anthropic Messages API over HTTPS with tool use. Non-streaming: the Analyst streams its own events to the browser."""
    name = "anthropic"
    ENDPOINT = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str):
        self._key = api_key
        self.model = model

    def chat(self, system: str, messages: list[dict], tools: list[dict], max_tokens: int, timeout: float) -> ProviderReply:
        import httpx
        try:
            r = httpx.post(self.ENDPOINT, headers={"x-api-key": self._key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                           json={"model": self.model, "max_tokens": max_tokens, "system": system, "messages": messages, "tools": tools}, timeout=timeout)
            r.raise_for_status()
            body = r.json()
        except Exception as e:  # noqa: BLE001 - never leak provider details or keys
            raise ProviderError("the language model request failed") from e
        blocks = body.get("content") or []
        usage = body.get("usage") or {}
        return ProviderReply(
            text="".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip(),
            tool_calls=[ToolCall(b["id"], b["name"], b.get("input") or {}) for b in blocks if b.get("type") == "tool_use"],
            usage={"input_tokens": int(usage.get("input_tokens", 0)), "output_tokens": int(usage.get("output_tokens", 0))},
            stop_reason=body.get("stop_reason"), message={"role": "assistant", "content": blocks})


def get_provider() -> Provider | None:
    """The configured provider, or None when no credentials exist (the Analyst then answers from retrieved records with its built-in rules)."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    return AnthropicProvider(key, os.environ.get("ANALYST_MODEL") or os.environ.get("ASSISTANT_MODEL") or "claude-sonnet-5-5")


def estimate_cost(usage: dict) -> float | None:
    """US dollars, only if the operator set per-million-token prices (ANALYST_PRICE_IN_PER_MTOK / ANALYST_PRICE_OUT_PER_MTOK). Otherwise unknown: no price is assumed."""
    try:
        pin, pout = float(os.environ["ANALYST_PRICE_IN_PER_MTOK"]), float(os.environ["ANALYST_PRICE_OUT_PER_MTOK"])
    except (KeyError, ValueError):
        return None
    return round((usage.get("input_tokens", 0) * pin + usage.get("output_tokens", 0) * pout) / 1_000_000, 6)


def status() -> dict[str, Any]:
    p = get_provider()
    return {"llm_configured": p is not None, "provider": p.name if p else None, "model": p.model if p else None}
