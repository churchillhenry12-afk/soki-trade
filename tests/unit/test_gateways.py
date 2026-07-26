from pathlib import Path
from typing import Any

import pytest
import qforge.gateways as gateways
from qforge.gateways import (
    GatewayConnectionError,
    GatewayManager,
    MT5Connection,
)


class BridgeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.headers = {"content-type": "application/json"}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class BridgeClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    async def __aenter__(self) -> "BridgeClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get(self, _url: str, *, headers: dict[str, str]) -> BridgeResponse:
        del headers
        return BridgeResponse(self.payload)


async def test_mt5_gateway_requires_explicit_demo_account(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = BridgeClient({"status": "ok", "account_mode": "UNKNOWN"})
    monkeypatch.setattr(gateways.httpx, "AsyncClient", lambda **_kwargs: client)
    manager = GatewayManager(tmp_path / "gateways.json")

    with pytest.raises(
        GatewayConnectionError,
        match="must verify account_mode=DEMO",
    ):
        await manager.connect_mt5(
            MT5Connection(
                transport="rest",
                endpoint="https://bridge.example",
                token="secret",
            )
        )

    status = manager.status()["mt5"]
    assert status["connected"] is False
    assert status["account_mode"] == "UNKNOWN"


async def test_mt5_gateway_accepts_verified_demo_account(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = BridgeClient({"status": "ok", "account_mode": "DEMO"})
    monkeypatch.setattr(gateways.httpx, "AsyncClient", lambda **_kwargs: client)
    manager = GatewayManager(tmp_path / "gateways.json")

    status = await manager.connect_mt5(
        MT5Connection(
            transport="rest",
            endpoint="https://bridge.example",
            token="secret",
        )
    )

    assert status["connected"] is True
    assert status["account_mode"] == "DEMO"
