from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import secrets
import shutil
from collections.abc import Awaitable, Callable
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


RuntimeActivity = Callable[[str, str, str, str], Awaitable[None]]


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
        self.capabilities: dict[str, Any] = {}

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
                response = await client.get(
                    f"{self.base_url}/v1/capabilities",
                    headers=self._headers(),
                )
                response.raise_for_status()
                body = response.json()
                if body.get("platform") != "hermes-agent":
                    raise ValueError("The configured endpoint is not a Hermes Agent runtime")
                if body.get("runtime", {}).get("tool_execution") != "server":
                    raise ValueError("Hermes server-side tool execution is unavailable")
                self.capabilities = body
            self.healthy = True
            self.last_error = ""
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            self.healthy = False
            self.capabilities = {}
            self.last_error = str(error)
        return self.healthy

    async def chat(
        self,
        message: str,
        *,
        history: list[dict[str, Any]],
        session_id: str,
        attachments: list[RuntimeAttachment] | None = None,
        on_activity: RuntimeActivity | None = None,
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
            "stream": True,
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
        text_parts: list[str] = []
        current_event = "message"
        response_session_id = session_id
        finish_reason = ""

        async def handle_event(event_name: str, data: str) -> None:
            nonlocal finish_reason
            if not data or data == "[DONE]":
                return
            body = json.loads(data)
            if event_name == "hermes.tool.progress":
                if on_activity is None:
                    return
                tool = str(body.get("tool", "tool"))
                tool_call_id = str(body.get("toolCallId", tool))
                tool_state = str(body.get("status", "running"))
                label = str(body.get("label") or f"Running {tool}")
                await on_activity(
                    f"hermes:{tool_call_id}",
                    label if tool_state == "running" else f"Finished {tool}",
                    "running" if tool_state == "running" else "completed",
                    tool,
                )
                return
            choices = body.get("choices", [])
            if not choices:
                return
            choice = choices[0]
            delta = choice.get("delta", {})
            content = delta.get("content")
            if content:
                text_parts.append(str(content))
            if choice.get("finish_reason"):
                finish_reason = str(choice["finish_reason"])

        async with (
            httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client,
            client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json=payload,
            ) as response,
        ):
            response.raise_for_status()
            response_session_id = response.headers.get(
                "X-Hermes-Session-Id",
                session_id,
            )
            data_lines: list[str] = []
            async for line in response.aiter_lines():
                if not line:
                    if data_lines:
                        await handle_event(current_event, "\n".join(data_lines))
                    current_event = "message"
                    data_lines = []
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    current_event = line.removeprefix("event:").strip()
                elif line.startswith("data:"):
                    data_lines.append(line.removeprefix("data:").lstrip())
            if data_lines:
                await handle_event(current_event, "\n".join(data_lines))

        text = "".join(text_parts).strip()
        if finish_reason == "error":
            raise ValueError("Hermes could not complete the tool run")
        if not text:
            raise ValueError("Hermes returned an empty response")
        return RuntimeReply(
            text=text,
            runtime="hermes-agent",
            session_id=response_session_id,
            completed=finish_reason not in {"error", "length"},
            partial=finish_reason == "length",
        )

    async def verify_agent(self) -> bool:
        if not await self.probe():
            return False
        try:
            reply = await self.chat(
                "Reply with exactly SOKI_HERMES_READY. Do not use tools.",
                history=[],
                session_id=f"soki-health-{uuid4().hex}",
            )
            if "SOKI_HERMES_READY" not in reply.text.upper():
                raise ValueError("Hermes model returned an unexpected readiness response")
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            self.healthy = False
            self.last_error = str(error)
            return False
        return True

    def status(self) -> dict[str, Any]:
        features = self.capabilities.get("features", {})
        runtime = self.capabilities.get("runtime", {})
        return {
            "status": "READY" if self.healthy else ("OFF" if not self.base_url else "UNAVAILABLE"),
            "adapter_kind": "hermes-http-runtime",
            "configured": self.configured,
            "verified": self.healthy,
            "url": self.base_url,
            "model": self.model,
            "last_error": self.last_error,
            "server_tools": runtime.get("tool_execution") == "server",
            "streaming": bool(features.get("chat_completions_streaming")),
            "approvals": bool(features.get("approval_events")),
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
        on_activity: RuntimeActivity | None = None,
    ) -> RuntimeReply:
        if self.hermes.healthy:
            try:
                return await self.hermes.chat(
                    message,
                    history=history,
                    session_id=session_id,
                    attachments=attachments,
                    on_activity=on_activity,
                )
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                self.hermes.healthy = False
                self.hermes.last_error = str(error)
        if _requires_agent_tools(message):
            reason = self.hermes.last_error or "Hermes is not connected"
            raise ValueError(
                "This request requires the Hermes tool runtime, but it is unavailable. "
                f"Open Settings and enable the installed Hermes Agent. Details: {reason}"
            )
        transcript = "\n".join(
            f"{item['role'].upper()}: {item['content']}" for item in history[-20:]
        )
        attachment_context = "\n\n".join(item.context_text() for item in (attachments or []))
        enriched_message = f"{message}\n\n{attachment_context}" if attachment_context else message
        prompt = f"{transcript}\nUSER: {enriched_message}" if transcript else enriched_message
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


def _requires_agent_tools(message: str) -> bool:
    direct_action = re.search(
        r"\b("
        r"execute|install|uninstall|click|download|upload|delete|move|rename|"
        r"patch|debug|deploy|automate|schedule|browse|inspect"
        r")\b",
        message,
        flags=re.IGNORECASE,
    )
    computer_object = re.search(
        r"\b(run|open|close|type|create|edit|fix|build|test|read|write|save)\b"
        r".{0,36}\b(file|folder|directory|project|repo|repository|code|app|"
        r"application|script|command|terminal|browser|website|tests?|computer)\b",
        message,
        flags=re.IGNORECASE,
    )
    return bool(direct_action or computer_object)


def discover_local_hermes() -> dict[str, str]:
    """Discover a locally installed Hermes API without exposing its secret."""
    hermes_home = Path(os.getenv("HERMES_HOME", "") or (Path.home() / ".hermes"))
    values: dict[str, str] = {}
    for config_path, delimiter in (
        (hermes_home / ".env", "="),
        (hermes_home / "config.yaml", ":"),
    ):
        if not config_path.is_file():
            continue
        try:
            for raw_line in config_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or delimiter not in line:
                    continue
                key, value = line.split(delimiter, 1)
                name = key.strip()
                if name.startswith("API_SERVER_"):
                    values[name] = value.strip().strip("'\"")
        except OSError:
            pass
    executable = os.getenv("HERMES_BIN", "").strip()
    path_executable = shutil.which("hermes")
    candidates = [
        Path(executable).expanduser() if executable else None,
        Path(path_executable) if path_executable else None,
        hermes_home / "hermes-agent" / "venv" / "bin" / "hermes",
        hermes_home / "hermes-agent" / "venv" / "Scripts" / "hermes.exe",
    ]
    binary = next((item for item in candidates if item and item.is_file()), None)
    enabled = values.get("API_SERVER_ENABLED", "").lower() in {"1", "true", "yes", "on"}
    key = values.get("API_SERVER_KEY", "")
    port = values.get("API_SERVER_PORT", "8642") or "8642"
    return {
        "installed": "true" if binary else "false",
        "binary": str(binary or ""),
        "enabled": "true" if enabled else "false",
        "api_key": key,
        "url": f"http://127.0.0.1:{port}",
    }


async def enable_local_hermes(
    *,
    model: str = "",
    base_url: str = "",
    model_api_key: str = "",
) -> dict[str, str]:
    """Enable the authenticated Hermes API and its computer-use toolset."""
    discovered = discover_local_hermes()
    binary = discovered["binary"]
    if not binary:
        raise RuntimeError("Hermes Agent is not installed on this computer")
    runtime_api_key = discovered["api_key"] or secrets.token_urlsafe(32)

    async def run(*arguments: str, timeout: float = 120) -> None:
        process = await asyncio.create_subprocess_exec(
            binary,
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
        if process.returncode:
            detail = output.decode("utf-8", errors="replace").strip()[-1200:]
            raise RuntimeError(detail or f"Hermes command failed ({process.returncode})")

    await run("config", "set", "API_SERVER_ENABLED", "true")
    await run("config", "set", "API_SERVER_KEY", runtime_api_key)
    await run("tools", "enable", "--platform", "api_server", "computer_use")
    normalized_url = base_url.rstrip("/")
    if model and normalized_url:
        if "api.xiaomimimo.com" in normalized_url and model_api_key:
            await run("config", "set", "XIAOMI_API_KEY", model_api_key)
            await run("config", "set", "model.provider", "xiaomi")
        else:
            await run("config", "set", "model.provider", "custom")
            if model_api_key:
                await run("config", "set", "model.api_key", model_api_key)
        await run("config", "set", "model.default", model)
        await run("config", "set", "model.base_url", normalized_url)
    await run("gateway", "restart")
    return {
        "url": discovered["url"],
        "api_key": runtime_api_key,
        "model": "hermes-agent",
    }


async def sync_local_hermes_model(
    *,
    model: str,
    base_url: str,
    api_key: str,
) -> bool:
    """Make Soki's verified model the model used by its bundled Hermes runtime."""
    discovered = discover_local_hermes()
    binary = discovered["binary"]
    if not binary or discovered["enabled"] != "true":
        return False

    async def run(*arguments: str, timeout: float = 120) -> None:
        process = await asyncio.create_subprocess_exec(
            binary,
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
        if process.returncode:
            detail = output.decode("utf-8", errors="replace").strip()[-1200:]
            raise RuntimeError(detail or f"Hermes command failed ({process.returncode})")

    normalized_url = base_url.rstrip("/")
    if "api.xiaomimimo.com" in normalized_url and api_key:
        await run("config", "set", "XIAOMI_API_KEY", api_key)
        await run("config", "set", "model.provider", "xiaomi")
    else:
        await run("config", "set", "model.provider", "custom")
        if api_key:
            await run("config", "set", "model.api_key", api_key)
    await run("config", "set", "model.default", model)
    await run("config", "set", "model.base_url", normalized_url)
    try:
        await run("gateway", "restart")
    except RuntimeError:
        await run("gateway", "install")
        await run("gateway", "start")
    return True


async def desktop_control_status() -> dict[str, Any]:
    """Return permission readiness for Hermes' optional computer-use driver."""
    path_binary = shutil.which("cua-driver")
    candidates = (
        Path(path_binary) if path_binary else None,
        Path.home() / ".local" / "bin" / "cua-driver",
        Path("/Applications/CuaDriver.app/Contents/MacOS/cua-driver"),
    )
    binary = next((item for item in candidates if item and item.is_file()), None)
    if binary is None:
        return {
            "installed": False,
            "ready": False,
            "permission_required": False,
            "status": "NOT_INSTALLED",
        }
    try:
        process = await asyncio.create_subprocess_exec(
            str(binary),
            "permissions",
            "status",
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        output, _ = await asyncio.wait_for(process.communicate(), timeout=4)
        payload = json.loads(output.decode("utf-8"))
        accessibility = bool(payload.get("accessibility"))
        screen_recording = bool(payload.get("screen_recording"))
        ready = accessibility and screen_recording
        return {
            "installed": True,
            "ready": ready,
            "permission_required": not ready,
            "status": "READY" if ready else "PERMISSION_REQUIRED",
            "accessibility": accessibility,
            "screen_recording": screen_recording,
        }
    except (OSError, TimeoutError, TypeError, ValueError, json.JSONDecodeError):
        return {
            "installed": True,
            "ready": False,
            "permission_required": True,
            "status": "UNKNOWN",
        }
