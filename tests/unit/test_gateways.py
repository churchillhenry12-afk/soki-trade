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


async def test_mt5_gateway_uses_selected_mode_when_bridge_does_not_report_one(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = BridgeClient({"status": "ok", "account_mode": "UNKNOWN"})
    monkeypatch.setattr(gateways.httpx, "AsyncClient", lambda **_kwargs: client)
    manager = GatewayManager(tmp_path / "gateways.json")

    status = await manager.connect_mt5(
        MT5Connection(
            transport="rest",
            endpoint="https://bridge.example",
            account_mode="DEMO",
            token="secret",
        )
    )

    assert status["connected"] is True
    assert status["account_mode"] == "DEMO"
    assert status["account_mode_source"] == "USER_SELECTED"
    assert status["read_only"] is True


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
                account_mode="DEMO",
                token="secret",
            )
        )

    assert status["connected"] is True
    assert status["account_mode"] == "DEMO"
    assert status["account_mode_source"] == "BRIDGE_VERIFIED"
    assert status["read_only"] is True


async def test_mt5_gateway_accepts_verified_real_account_as_read_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = BridgeClient({"status": "ok", "account_info": {"trade_mode": 2}})
    monkeypatch.setattr(gateways.httpx, "AsyncClient", lambda **_kwargs: client)
    manager = GatewayManager(tmp_path / "gateways.json")

    status = await manager.connect_mt5(
        MT5Connection(
            transport="rest",
            endpoint="https://bridge.example",
            account_mode="REAL",
            token="secret",
        )
    )

    assert status["connected"] is True
    assert status["account_mode"] == "REAL"
    assert status["account_mode_source"] == "BRIDGE_VERIFIED"
    assert status["read_only"] is True


async def test_mt5_gateway_rejects_account_mode_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = BridgeClient({"status": "ok", "account_mode": "REAL"})
    monkeypatch.setattr(gateways.httpx, "AsyncClient", lambda **_kwargs: client)
    manager = GatewayManager(tmp_path / "gateways.json")

    with pytest.raises(
        GatewayConnectionError,
        match="reports a REAL account, but DEMO was selected",
    ):
        await manager.connect_mt5(
            MT5Connection(
                transport="rest",
                endpoint="https://bridge.example",
                account_mode="DEMO",
                token="secret",
            )
        )

    status = manager.status()["mt5"]
    assert status["connected"] is False
    assert status["account_mode"] == "DEMO"
    assert status["account_mode_source"] == "UNVERIFIED"
