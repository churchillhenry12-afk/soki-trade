from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from os import chmod, getenv
from pathlib import Path
from typing import Any, Literal, Protocol, cast

import httpx

ProviderKind = Literal["mock", "openai_compatible", "anthropic", "local"]


class ModelProvider(Protocol):
    name: str

    async def complete(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class ModelAssignment:
    agent: str
    provider: str
    model: str


@dataclass(frozen=True)
class ProviderConfiguration:
    provider: ProviderKind = "mock"
    model: str = "deterministic-mock"
    base_url: str = ""
    api_key: str = ""

    @property
    def is_mock(self) -> bool:
        return self.provider == "mock"

    def public_status(self) -> dict[str, str | bool]:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "configured": self.is_mock or bool(self.model and self.base_url),
            "api_key_present": bool(self.api_key),
            "secret_storage": "LOCAL_0600",
        }


class MockModelProvider:
    name = "mock"

    async def complete(self, prompt: str) -> str:
        return (
            "SOKI TRADE MOCK DIRECTOR // Message received. "
            f"Input length={len(prompt)}. Configure a model API in SETUP for live model replies."
        )


class ModelRouter:
    def __init__(self, config_path: Path | None = None) -> None:
        configured_path = getenv("QFORGE_PROVIDER_CONFIG_PATH", "data/provider-config.json")
        self.config_path = config_path or Path(configured_path)
        self.providers: dict[str, ModelProvider] = {"mock": MockModelProvider()}
        self.configuration = self._load_configuration()

    def assignment(self, agent: str) -> ModelAssignment:
        provider = getenv(f"QFORGE_{agent}_PROVIDER", self.configuration.provider)
        model = getenv(f"QFORGE_{agent}_MODEL", self.configuration.model)
        if provider not in {"mock", "openai_compatible", "anthropic", "local"}:
            raise ValueError(f"model provider is not configured: {provider}")
        return ModelAssignment(agent=agent, provider=provider, model=model)

    def status(self) -> dict[str, str | bool]:
        return self.configuration.public_status()

    def configure(
        self,
        *,
        provider: ProviderKind,
        model: str,
        base_url: str,
        api_key: str | None,
        persist: bool,
    ) -> dict[str, str | bool]:
        normalized_model = model.strip()
        normalized_url = base_url.strip().rstrip("/")
        if provider == "mock":
            normalized_model = normalized_model or "deterministic-mock"
            normalized_url = ""
        else:
            if not normalized_model:
                raise ValueError("model name is required")
            if not normalized_url.startswith(("http://", "https://")):
                raise ValueError("base URL must start with http:// or https://")
        preserved_key = (
            self.configuration.api_key
            if api_key is None and self.configuration.provider == provider
            else api_key or ""
        )
        if provider in {"openai_compatible", "anthropic"} and not preserved_key:
            raise ValueError("an API key is required for this provider")
        self.configuration = ProviderConfiguration(
            provider=provider,
            model=normalized_model,
            base_url=normalized_url,
            api_key=preserved_key,
        )
        if persist:
            self._save_configuration()
        return self.status()

    async def discover_models(
        self,
        *,
        provider: ProviderKind,
        base_url: str,
        api_key: str | None,
    ) -> list[str]:
        if provider == "mock":
            raise ValueError("select a real or local model provider")
        normalized_url = base_url.strip().rstrip("/")
        if not normalized_url.startswith(("http://", "https://")):
            raise ValueError("base URL must start with http:// or https://")
        preserved_key = (
            self.configuration.api_key
            if api_key is None and self.configuration.provider == provider
            else api_key or ""
        )
        if provider in {"openai_compatible", "anthropic"} and not preserved_key:
            raise ValueError("an API key is required to scan this provider")

        headers: dict[str, str] = {"accept": "application/json"}
        if provider == "anthropic":
            endpoint = _endpoint(normalized_url, "models", ensure_version=True)
            headers.update(
                {
                    "x-api-key": preserved_key,
                    "anthropic-version": "2023-06-01",
                }
            )
        else:
            endpoint = _endpoint(normalized_url, "models")
            if preserved_key:
                headers["authorization"] = f"Bearer {preserved_key}"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(endpoint, headers=headers)
            response.raise_for_status()
        body: dict[str, Any] = response.json()
        models = _model_ids(body)
        if not models:
            raise ValueError("provider returned no selectable models")
        return models

    async def complete(self, prompt: str, *, system_prompt: str | None = None) -> str:
        config = self.configuration
        if config.provider == "mock":
            return await self.providers["mock"].complete(prompt)
        if config.provider == "anthropic":
            return await self._anthropic_complete(prompt, system_prompt=system_prompt)
        return await self._openai_compatible_complete(prompt, system_prompt=system_prompt)

    async def _openai_compatible_complete(self, prompt: str, *, system_prompt: str | None) -> str:
        config = self.configuration
        endpoint = _endpoint(config.base_url, "chat/completions")
        headers = {"content-type": "application/json"}
        if config.api_key:
            headers["authorization"] = f"Bearer {config.api_key}"
        payload = {
            "model": config.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt or _DEFAULT_SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
        body: dict[str, Any] = response.json()
        try:
            return str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError("provider returned an invalid chat-completions response") from error

    async def _anthropic_complete(self, prompt: str, *, system_prompt: str | None) -> str:
        config = self.configuration
        endpoint = _endpoint(config.base_url, "messages", ensure_version=True)
        headers = {
            "content-type": "application/json",
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": config.model,
            "max_tokens": 1024,
            "system": system_prompt or _DEFAULT_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
        body: dict[str, Any] = response.json()
        try:
            blocks = body["content"]
            return "\n".join(
                str(block["text"])
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "text"
            )
        except (KeyError, TypeError) as error:
            raise ValueError("provider returned an invalid messages response") from error

    def _load_configuration(self) -> ProviderConfiguration:
        if not self.config_path.exists():
            return ProviderConfiguration()
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
            provider = str(payload["provider"])
            if provider not in {"mock", "openai_compatible", "anthropic", "local"}:
                return ProviderConfiguration()
            return ProviderConfiguration(
                provider=cast(ProviderKind, provider),
                model=str(payload["model"]),
                base_url=str(payload.get("base_url", "")),
                api_key=str(payload.get("api_key", "")),
            )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return ProviderConfiguration()

    def _save_configuration(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        chmod(self.config_path.parent, 0o700)
        self.config_path.touch(exist_ok=True, mode=0o600)
        chmod(self.config_path, 0o600)
        self.config_path.write_text(
            json.dumps(asdict(self.configuration), indent=2),
            encoding="utf-8",
        )
        chmod(self.config_path, 0o600)


def _endpoint(base_url: str, resource: str, *, ensure_version: bool = False) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith(resource):
        return normalized
    if ensure_version and not normalized.endswith("/v1"):
        normalized = f"{normalized}/v1"
    return f"{normalized}/{resource}"


def _model_ids(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data", [])
    if not isinstance(data, list):
        raise ValueError("provider returned an invalid model catalog")
    model_ids = {
        str(item["id"]).strip()
        for item in data
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }
    return sorted(model_ids, key=str.casefold)


_DEFAULT_SYSTEM_PROMPT = (
    "You are soki code, a capable general-purpose AI operations agent with specialist "
    "trading-research skills. Help with normal questions, planning, writing, analysis, "
    "and the connected tools exposed by soki code. Be direct and practical. Never claim "
    "that an external action or connection succeeded unless the application confirms it. "
    "Return a complete human-readable answer only; never emit tool-call XML, function tags, "
    "or internal tool names. "
    "For trading, distinguish research and PAPER workflows from live execution; never "
    "claim live trading is enabled."
)
