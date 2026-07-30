from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from qforge.model_router import ModelRouter

SOKI_SYSTEM_PROMPT = """
You are soki code, an evidence-first operating agent built on the Hermes runtime.
Turn requests into completed outcomes. Before answering, determine the success
conditions, use available tools when useful, check the result, and state any
unfinished work honestly. Never claim a tool action happened without evidence.
Trading work is research-only: never place live orders, bypass approval, or
override the soki code risk governor.
""".strip()


@dataclass(frozen=True)
class RuntimeReply:
    text: str
    runtime: str
    session_id: str
    completed: bool = True
    partial: bool = False


@dataclass(frozen=True)
class RuntimeAttachment:
    name: str
    media_type: str
    kind: str
    path: Path
    size_bytes: int

    def context_text(self) -> str:
        details = (
            f"Attached {self.kind.lower()}: {self.name} "
            f"({self.media_type}, {self.size_bytes} bytes)."
        )
        if self.kind != "DOCUMENT" or self.size_bytes > 1_000_000:
            return details
        try:
            text = self.path.read_text(encoding="utf-8", errors="replace")[:100_000]
        except OSError:
            return details
        return f"{details}\n<attachment name={self.name!r}>\n{text}\n</attachment>"


class HermesRuntimeClient:
    """Upgrade-safe client for Hermes Agent's authenticated HTTP runtime."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.last_error = ""
        self.healthy = False

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    def _headers(self, session_id: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if session_id:
            headers["X-Hermes-Session-Id"] = session_id
            headers["X-Hermes-Session-Key"] = f"soki:{session_id}"
        return headers

    async def probe(self) -> bool:
        if not self.configured:
            self.healthy = False
            self.last_error = "Hermes URL and API key are required"
            return False
        try:
            async with httpx.AsyncClient(
                timeout=min(self.timeout_seconds, 8),
                transport=self.transport,
            ) as client:
                response = await client.get(f"{self.base_url}/health", headers=self._headers())
                response.raise_for_status()
            self.healthy = True
            self.last_error = ""
        except httpx.HTTPError as error:
            self.healthy = False
            self.last_error = str(error)
        return self.healthy

    async def chat(
        self,
        message: str,
        *,
        history: list[dict[str, Any]],
        session_id: str,
        attachments: list[RuntimeAttachment] | None = None,
    ) -> RuntimeReply:
        attached = attachments or []
        user_content: str | list[dict[str, Any]]
        if attached:
            text_context = "\n\n".join(item.context_text() for item in attached)
            user_content = [{"type": "text", "text": f"{message}\n\n{text_context}"}]
            for item in attached:
                if item.kind != "IMAGE" or item.size_bytes > 20_000_000:
                    continue
                encoded = base64.b64encode(item.path.read_bytes()).decode("ascii")
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{item.media_type};base64,{encoded}"},
                    }
                )
        else:
            user_content = message
        payload: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": SOKI_SYSTEM_PROMPT},
                *history[-20:],
                {"role": "user", "content": user_content},
            ],
        }
        headers = {
            **self._headers(session_id),
            "Idempotency-Key": f"soki-{session_id}-{uuid4().hex}",
        }
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
        body = response.json()
        text = str(body["choices"][0]["message"]["content"]).strip()
        if not text:
            raise ValueError("Hermes returned an empty response")
        return RuntimeReply(
            text=text,
            runtime="hermes-agent",
            session_id=response.headers.get("X-Hermes-Session-Id", session_id),
            completed=response.headers.get("X-Hermes-Completed", "true") != "false",
            partial=response.headers.get("X-Hermes-Partial", "false") == "true",
        )

    def status(self) -> dict[str, str | bool]:
        return {
            "status": "READY" if self.healthy else ("OFF" if not self.base_url else "UNAVAILABLE"),
            "adapter_kind": "hermes-http-runtime",
            "configured": self.configured,
            "verified": self.healthy,
            "url": self.base_url,
            "model": self.model,
            "last_error": self.last_error,
        }


class SokiAgentRuntime:
    """Hermes-first agent runtime with a deliberate model-router fallback."""

    def __init__(self, hermes: HermesRuntimeClient, fallback: ModelRouter) -> None:
        self.hermes = hermes
        self.fallback = fallback

    async def chat(
        self,
        message: str,
        *,
        history: list[dict[str, Any]],
        session_id: str,
        attachments: list[RuntimeAttachment] | None = None,
    ) -> RuntimeReply:
        if self.hermes.healthy:
            try:
                return await self.hermes.chat(
                    message,
                    history=history,
                    session_id=session_id,
                    attachments=attachments,
                )
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                self.hermes.healthy = False
                self.hermes.last_error = str(error)
        transcript = "\n".join(
            f"{item['role'].upper()}: {item['content']}" for item in history[-20:]
        )
        attachment_context = "\n\n".join(
            item.context_text() for item in (attachments or [])
        )
        enriched_message = (
            f"{message}\n\n{attachment_context}" if attachment_context else message
        )
        prompt = (
            f"{transcript}\nUSER: {enriched_message}"
            if transcript
            else enriched_message
        )
        text = await self.fallback.complete(prompt, system_prompt=SOKI_SYSTEM_PROMPT)
        if not text.strip():
            raise ValueError("model provider returned an empty response")
        return RuntimeReply(
            text=text.strip(),
            runtime="model-router-fallback",
            session_id=session_id,
        )


# Compatibility for callers created before the product name was corrected.
SokyAgentRuntime = SokiAgentRuntime
