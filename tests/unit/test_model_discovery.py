from pathlib import Path
from typing import Any

import qforge.model_router as model_router
from qforge.model_router import ModelRouter, _model_ids


class CatalogResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class CatalogClient:
    def __init__(self, payload: dict[str, Any], requests: list[tuple[str, dict[str, str]]]) -> None:
        self.payload = payload
        self.requests = requests

    async def __aenter__(self) -> "CatalogClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get(self, endpoint: str, *, headers: dict[str, str]) -> CatalogResponse:
        self.requests.append((endpoint, headers))
        return CatalogResponse(self.payload)


def test_model_catalog_is_deduplicated_and_sorted() -> None:
    payload = {
        "data": [
            {"id": "zeta-model"},
            {"id": "Alpha-model"},
            {"id": "zeta-model"},
            {"display_name": "missing id"},
        ]
    }

    assert _model_ids(payload) == ["Alpha-model", "zeta-model"]


async def test_local_model_discovery_calls_openai_compatible_catalog(
    tmp_path: Path,
    monkeypatch,
) -> None:
    requests: list[tuple[str, dict[str, str]]] = []
    client = CatalogClient({"data": [{"id": "qwen:14b"}, {"id": "llama:8b"}]}, requests)
    monkeypatch.setattr(model_router.httpx, "AsyncClient", lambda **_kwargs: client)
    router = ModelRouter(tmp_path / "provider.json")

    models = await router.discover_models(
        provider="local",
        base_url="http://127.0.0.1:11434/v1/",
        api_key=None,
    )

    assert models == ["llama:8b", "qwen:14b"]
    assert requests == [
        (
            "http://127.0.0.1:11434/v1/models",
            {"accept": "application/json"},
        )
    ]


async def test_anthropic_model_discovery_uses_provider_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    requests: list[tuple[str, dict[str, str]]] = []
    client = CatalogClient({"data": [{"id": "claude-sonnet"}]}, requests)
    monkeypatch.setattr(model_router.httpx, "AsyncClient", lambda **_kwargs: client)
    router = ModelRouter(tmp_path / "provider.json")

    models = await router.discover_models(
        provider="anthropic",
        base_url="https://api.anthropic.com",
        api_key="provider-secret",
    )

    assert models == ["claude-sonnet"]
    assert requests[0][0] == "https://api.anthropic.com/v1/models"
    assert requests[0][1]["x-api-key"] == "provider-secret"
    assert requests[0][1]["anthropic-version"] == "2023-06-01"
