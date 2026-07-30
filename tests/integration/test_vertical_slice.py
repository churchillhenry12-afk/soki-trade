from __future__ import annotations

import json
from base64 import urlsafe_b64decode
from os import stat
from pathlib import Path
from stat import S_IMODE
from time import monotonic, sleep

from fastapi.testclient import TestClient
from qforge_api.main import app


def compact_pairing_payload(raw: str) -> dict[str, str]:
    prefix, version, pairing_token, code, *encoded_url = raw.split(":")
    assert (prefix, version) == ("soki", "1")
    pairing_bytes = urlsafe_b64decode(pairing_token + "=" * (-len(pairing_token) % 4))
    pairing_id = (
        f"{pairing_bytes.hex()[:8]}-{pairing_bytes.hex()[8:12]}-"
        f"{pairing_bytes.hex()[12:16]}-{pairing_bytes.hex()[16:20]}-"
        f"{pairing_bytes.hex()[20:]}"
    )
    api_base_url = "http://127.0.0.1:8000"
    if encoded_url:
        url_token = encoded_url[0]
        api_base_url = urlsafe_b64decode(url_token + "=" * (-len(url_token) % 4)).decode()
    return {"pairing_id": pairing_id, "code": code, "api_base_url": api_base_url}


def test_vertical_slice_reaches_a_deterministic_risk_decision(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QFORGE_DATABASE_URL", f"sqlite:///{tmp_path / 'qforge-test.db'}")
    monkeypatch.setenv("QFORGE_DEMO_MODE", "true")
    with TestClient(app) as client:
        objective_response = client.post(
            "/research/objectives",
            json={
                "title": "EURUSD resilience",
                "thesis": "Find crossover candidates that survive execution-cost stress.",
                "symbols": ["EURUSD"],
                "timeframe": "M15",
            },
        )
        assert objective_response.status_code == 201
        experiment_response = client.post(
            "/experiments",
            json={"objective_id": objective_response.json()["objective_id"], "seed": 42},
        )
        assert experiment_response.status_code == 201
        experiment_id = experiment_response.json()["experiment_id"]
        assert client.post(f"/experiments/{experiment_id}/start").status_code == 200

        deadline = monotonic() + 20
        experiment = {}
        while monotonic() < deadline:
            experiment = client.get(f"/experiments/{experiment_id}").json()
            if experiment["state"] in {
                "AWAITING_HUMAN_APPROVAL",
                "REJECTED",
                "FAILED",
            }:
                break
            sleep(0.05)

        assert experiment["state"] in {"AWAITING_HUMAN_APPROVAL", "REJECTED"}
        assert experiment["report"] is not None
        assert len(experiment["report"]["strategies"]) == 3
        assert len(experiment["report"]["backtests"]) == 3
        assert experiment["report"]["solver_benchmark"]["validation_required"] is True
        assert (
            experiment["report"]["solver_benchmark"]["solvers"]["mock_qubo_exhaustive"]["verified"]
            is False
        )
        events = client.get(f"/experiments/{experiment_id}/events").json()
        assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
        assert any(event["event_type"] == "stress_test.completed" for event in events)
        assert any(event["agent"] == "RISK_GOVERNOR" for event in events)
        assert all(event["payload"].get("orders_placed", 0) == 0 for event in events)


def test_terminal_model_setup_and_mock_chat(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "provider-config.json"
    monkeypatch.setenv("QFORGE_DATABASE_URL", f"sqlite:///{tmp_path / 'qforge-chat.db'}")
    monkeypatch.setenv("QFORGE_PROVIDER_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("QFORGE_DEMO_MODE", "true")
    with TestClient(app) as client:
        setup_response = client.post(
            "/models/config",
            json={
                "provider": "mock",
                "model": "deterministic-mock",
                "base_url": "",
                "api_key": None,
                "persist": True,
            },
        )
        assert setup_response.status_code == 200
        assert setup_response.json()["provider"] == "mock"
        assert "api_key" not in setup_response.json()
        assert S_IMODE(stat(config_path).st_mode) == 0o600

        chat_response = client.post(
            "/chat",
            json={"message": "How should I stress-test EURUSD?", "history": []},
        )
        assert chat_response.status_code == 200
        assert chat_response.json()["mock"] is True
        assert "Configure a model API in SETUP" in chat_response.json()["reply"]


def test_production_runtime_is_ready_without_optional_ai(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QFORGE_DATABASE_URL", f"sqlite:///{tmp_path / 'qforge-prod.db'}")
    monkeypatch.setenv("QFORGE_PROVIDER_CONFIG_PATH", str(tmp_path / "provider.json"))
    monkeypatch.setenv("QFORGE_MARKET_DATA_DIRECTORY", str(tmp_path / "market"))
    monkeypatch.setenv("QFORGE_DEMO_MODE", "false")
    with TestClient(app) as client:
        status_response = client.get("/system/status")
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["runtime"] == "PRODUCTION"
        assert status["hermes"]["status"] == "OFF"
        assert status["hermes"]["adapter_kind"] == "hermes-http-runtime"
        assert status["market_data"]["status"] == "READY"
        assert status["market_data"]["source"] == "PUBLIC_FEED"
        assert status["quantum"]["status"] == "DISABLED"
        assert status["mt5"]["status"] == "DISABLED"

        ready_response = client.get("/ready")
        assert ready_response.status_code == 200
        assert ready_response.json() == {"status": "ready", "blockers": []}


def test_agent_chat_starts_research_and_explains_the_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QFORGE_DATABASE_URL", f"sqlite:///{tmp_path / 'qforge-agent.db'}")
    monkeypatch.setenv("QFORGE_PROVIDER_CONFIG_PATH", str(tmp_path / "provider.json"))
    monkeypatch.setenv("QFORGE_GATEWAY_CONFIG_PATH", str(tmp_path / "gateways.json"))
    monkeypatch.setenv("QFORGE_DEMO_MODE", "true")
    with TestClient(app) as client:
        response = client.post(
            "/agent/chat",
            json={
                "message": "Backtest EURUSD M15 with realistic execution stress",
                "history": [],
                "experiment_id": None,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["action"] == "EXPERIMENT_STARTED"
        experiment_id = body["experiment_id"]

        deadline = monotonic() + 20
        experiment = {}
        while monotonic() < deadline:
            experiment = client.get(f"/experiments/{experiment_id}").json()
            if experiment["state"] in {"AWAITING_HUMAN_APPROVAL", "REJECTED", "FAILED"}:
                break
            sleep(0.05)
        assert experiment["report"] is not None

        report = client.post(
            "/agent/chat",
            json={
                "message": "Show me the report",
                "history": [],
                "experiment_id": experiment_id,
            },
        )
        assert report.status_code == 200
        assert report.json()["action"] == "REPORT"
        assert "strongest candidate" in report.json()["reply"]


def test_agent_chat_manages_connections_and_general_tasks(tmp_path: Path, monkeypatch) -> None:
    gateway_path = tmp_path / "gateways.json"
    gateway_path.write_text(
        json.dumps(
            {
                "telegram": {
                    "token": "telegram-secret",
                    "chat_id": "12345",
                    "connected": True,
                    "bot_username": "soki_test_bot",
                },
                "mt5": {
                    "transport": "mcp",
                    "endpoint": "https://bridge.example",
                    "token": "mt5-secret",
                    "connected": True,
                    "account_mode": "DEMO",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("QFORGE_DATABASE_URL", f"sqlite:///{tmp_path / 'qforge-agent-tools.db'}")
    monkeypatch.setenv("QFORGE_PROVIDER_CONFIG_PATH", str(tmp_path / "provider.json"))
    monkeypatch.setenv("QFORGE_GATEWAY_CONFIG_PATH", str(gateway_path))
    monkeypatch.setenv("QFORGE_DEMO_MODE", "true")
    with TestClient(app) as client:
        disconnected = client.post(
            "/agent/chat",
            json={
                "message": "Disconnect my Telegram account",
                "history": [],
                "experiment_id": None,
            },
        )
        assert disconnected.status_code == 200
        assert disconnected.json()["action"] == "CONNECTION_CHANGED"
        assert client.get("/setup/status").json()["telegram"]["connected"] is False

        connect_mt5 = client.post(
            "/agent/chat",
            json={
                "message": "Connect MT5",
                "history": [],
                "experiment_id": None,
            },
        )
        assert connect_mt5.status_code == 200
        assert connect_mt5.json()["action"] == "CONNECTION_SETUP"
        assert connect_mt5.json()["client_action"] == "CONNECT_MT5"

        mt5_status = client.post(
            "/agent/chat",
            json={
                "message": "Are we connected to MT5?",
                "history": [],
                "experiment_id": None,
            },
        )
        assert mt5_status.status_code == 200
        assert mt5_status.json()["action"] == "STATUS"
        assert "MT5 is connected through MCP" in mt5_status.json()["reply"]
        assert "<tool_call>" not in mt5_status.json()["reply"]

        general = client.post(
            "/agent/chat",
            json={
                "message": "Help me write a public launch checklist",
                "history": [],
                "experiment_id": None,
            },
        )
        assert general.status_code == 200
        assert general.json()["action"] == "MESSAGE"
        assert "MOCK DIRECTOR" in general.json()["reply"]

        with client.stream(
            "POST",
            "/agent/chat/stream",
            json={
                "message": "Help me write a concise release note",
                "history": [],
                "experiment_id": None,
                "session_id": "stream-integration-test",
            },
        ) as streamed:
            assert streamed.status_code == 200
            events = [json.loads(line) for line in streamed.iter_lines() if line]
        activities = [
            event["activity"]
            for event in events
            if event.get("type") == "activity"
        ]
        assert {activity["id"] for activity in activities} >= {
            "proof",
            "understand",
            "work",
            "runtime",
            "inspect",
        }
        assert any(
            activity["id"] == "runtime" and activity["state"] == "running"
            for activity in activities
        )
        assert any(
            activity["id"] == "work" and activity["state"] == "running"
            for activity in activities
        )
        result = next(event["response"] for event in events if event["type"] == "result")
        assert result["proof"]["status"] == "VERIFIED"

        phone = client.post(
            "/agent/chat",
            json={"message": "Pair my Android phone", "history": []},
        )
        assert phone.status_code == 200
        assert phone.json()["client_action"] == "PAIR_PHONE"

        hermes = client.post(
            "/agent/chat",
            json={"message": "Configure Hermes", "history": []},
        )
        assert hermes.status_code == 200
        assert hermes.json()["client_action"] == "CONNECT_HERMES"
        assert general.json()["proof"]["status"] == "VERIFIED"
        assert general.json()["task_id"]

        async def raw_tool_call(_prompt: str, *, system_prompt: str | None = None) -> str:
            del system_prompt
            return (
                "<tool_call>\n<function=list_connections>\n"
                "</function>\n</tool_call>"
            )

        monkeypatch.setattr(app.state.model_router, "complete", raw_tool_call)
        recovered = client.post(
            "/agent/chat",
            json={
                "message": "What services are available right now?",
                "history": [],
                "experiment_id": None,
            },
        )
        assert recovered.status_code == 200
        assert recovered.json()["action"] == "STATUS"
        assert "Telegram is not connected" in recovered.json()["reply"]
        assert "<tool_call>" not in recovered.json()["reply"]

        async def unknown_tool(_prompt: str, *, system_prompt: str | None = None) -> str:
            del system_prompt
            return "<tool_call><function=unsupported_action></function></tool_call>"

        monkeypatch.setattr(app.state.model_router, "complete", unknown_tool)
        unsupported = client.post(
            "/agent/chat",
            json={
                "message": "Take care of the next step",
                "history": [],
                "experiment_id": None,
            },
        )
        assert unsupported.status_code == 200
        assert unsupported.json()["action"] == "MESSAGE"
        assert "could not safely complete" in unsupported.json()["reply"]
        assert "<tool_call>" not in unsupported.json()["reply"]

        async def empty_reply(_prompt: str, *, system_prompt: str | None = None) -> str:
            del system_prompt
            return "  "

        monkeypatch.setattr(app.state.model_router, "complete", empty_reply)
        empty = client.post(
            "/agent/chat",
            json={
                "message": "Give me a useful answer",
                "history": [],
                "experiment_id": None,
            },
        )
        assert empty.status_code == 502
        assert empty.json()["detail"] == "model provider returned an empty response"

    saved = gateway_path.read_text(encoding="utf-8")
    assert "telegram-secret" not in saved
    assert "mt5-secret" in saved


def test_setup_status_does_not_return_gateway_secrets(tmp_path: Path, monkeypatch) -> None:
    gateway_path = tmp_path / "gateways.json"
    gateway_path.write_text(
        json.dumps(
            {
                "telegram": {
                    "token": "telegram-secret",
                    "chat_id": "12345",
                    "connected": False,
                    "bot_username": "qforge_test_bot",
                },
                "mt5": {
                    "transport": "rest",
                    "endpoint": "https://bridge.example",
                    "token": "mt5-secret",
                    "connected": True,
                    "account_mode": "DEMO",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("QFORGE_DATABASE_URL", f"sqlite:///{tmp_path / 'qforge-setup.db'}")
    monkeypatch.setenv("QFORGE_PROVIDER_CONFIG_PATH", str(tmp_path / "provider.json"))
    monkeypatch.setenv("QFORGE_GATEWAY_CONFIG_PATH", str(gateway_path))
    monkeypatch.setenv("QFORGE_DEMO_MODE", "true")
    with TestClient(app) as client:
        response = client.get("/setup/status")
        assert response.status_code == 200
        serialized = response.text
        assert "telegram-secret" not in serialized
        assert "mt5-secret" not in serialized
        assert response.json()["telegram"]["bot_username"] == "qforge_test_bot"
        assert response.json()["mt5"]["account_mode"] == "DEMO"

        local_mt5 = client.get("/mt5/local-status")
        assert local_mt5.status_code == 200
        assert local_mt5.json()["bridge_required"] is False
        assert local_mt5.json()["gateway_connected"] is True


def test_mt5_api_requires_and_forwards_selected_account_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("QFORGE_DATABASE_URL", f"sqlite:///{tmp_path / 'qforge-mt5-mode.db'}")
    monkeypatch.setenv("QFORGE_GATEWAY_CONFIG_PATH", str(tmp_path / "gateways.json"))
    monkeypatch.setenv("QFORGE_DEMO_MODE", "true")
    captured: dict[str, str] = {}

    async def connect_mt5(connection) -> dict[str, str | bool]:  # type: ignore[no-untyped-def]
        captured["account_mode"] = connection.account_mode
        return {
            "configured": True,
            "connected": True,
            "account_mode": connection.account_mode,
            "account_mode_source": "USER_SELECTED",
            "read_only": True,
        }

    with TestClient(app) as client:
        monkeypatch.setattr(app.state.gateways, "connect_mt5", connect_mt5)
        response = client.post(
            "/gateways/mt5/connect",
            json={
                "transport": "rest",
                "endpoint": "http://127.0.0.1:8765",
                "account_mode": "REAL",
                "token": None,
            },
        )
        missing_mode = client.post(
            "/gateways/mt5/connect",
            json={
                "transport": "rest",
                "endpoint": "http://127.0.0.1:8765",
                "token": None,
            },
        )

    assert response.status_code == 200
    assert response.json()["account_mode"] == "REAL"
    assert response.json()["read_only"] is True
    assert captured["account_mode"] == "REAL"
    assert missing_mode.status_code == 422


def test_verified_hosted_ui_can_preflight_local_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QFORGE_DATABASE_URL", f"sqlite:///{tmp_path / 'qforge-cors.db'}")
    monkeypatch.setenv("QFORGE_PROVIDER_CONFIG_PATH", str(tmp_path / "provider.json"))
    monkeypatch.setenv("QFORGE_GATEWAY_CONFIG_PATH", str(tmp_path / "gateways.json"))
    monkeypatch.setenv("QFORGE_DEMO_MODE", "true")
    with TestClient(app) as client:
        response = client.options(
            "/setup/status",
            headers={
                "Origin": "https://soki-trade-agent.vercel.app",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Private-Network": "true",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "https://soki-trade-agent.vercel.app"
    )
    assert response.headers["access-control-allow-private-network"] == "true"


def test_qr_pairing_is_one_time_authenticated_and_revocable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("QFORGE_DATABASE_URL", f"sqlite:///{tmp_path / 'pairing.db'}")
    monkeypatch.setenv("QFORGE_GATEWAY_CONFIG_PATH", str(tmp_path / "gateways.json"))
    monkeypatch.setenv("QFORGE_DEMO_MODE", "true")
    with TestClient(app) as client:
        created = client.post(
            "/pairing/sessions",
            json={"api_base_url": "http://127.0.0.1:8000"},
        )
        assert created.status_code == 201
        qr_payload = compact_pairing_payload(created.json()["qr_payload"])
        assert qr_payload["api_base_url"] == "http://127.0.0.1:8000"

        claim = client.post(
            "/pairing/claim",
            json={
                "pairing_id": qr_payload["pairing_id"],
                "code": qr_payload["code"],
                "device_name": "Pixel test",
            },
        )
        assert claim.status_code == 200
        token = claim.json()["device_token"]
        device_id = claim.json()["device_id"]

        repeated = client.post(
            "/pairing/claim",
            json={
                "pairing_id": qr_payload["pairing_id"],
                "code": qr_payload["code"],
                "device_name": "Second device",
            },
        )
        assert repeated.status_code == 410

        missing_auth = client.get("/mobile/status")
        assert missing_auth.status_code == 401
        status_response = client.get(
            "/mobile/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert status_response.status_code == 200
        assert status_response.json()["device"]["name"] == "Pixel test"

        devices = client.get("/devices")
        assert devices.status_code == 200
        assert devices.json()[0]["device_id"] == device_id
        assert "device_token" not in devices.text

        assert client.delete(f"/devices/{device_id}").status_code == 200
        revoked = client.get(
            "/mobile/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert revoked.status_code == 401


def test_attachments_are_stored_forwarded_and_isolated_by_device(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("QFORGE_DATABASE_URL", f"sqlite:///{tmp_path / 'attachments.db'}")
    monkeypatch.setenv("QFORGE_GATEWAY_CONFIG_PATH", str(tmp_path / "gateways.json"))
    monkeypatch.setenv("QFORGE_ATTACHMENT_DIRECTORY", str(tmp_path / "attachments"))
    monkeypatch.setenv("QFORGE_DEMO_MODE", "true")
    captured: dict[str, str] = {}

    async def capture_prompt(prompt: str, *, system_prompt: str | None = None) -> str:
        del system_prompt
        captured["prompt"] = prompt
        return "I read the attachment."

    with TestClient(app) as client:
        local_upload = client.post(
            "/attachments",
            files={"file": ("notes.txt", b"important launch detail", "text/plain")},
        )
        assert local_upload.status_code == 201
        local_attachment = local_upload.json()
        assert local_attachment["kind"] == "DOCUMENT"
        assert local_attachment["size_bytes"] == len(b"important launch detail")
        assert client.get(local_attachment["download_url"]).content == b"important launch detail"

        rejected = client.post(
            "/attachments",
            files={"file": ("unsafe.exe", b"MZ", "application/x-msdownload")},
        )
        assert rejected.status_code == 415

        monkeypatch.setattr(app.state.model_router, "complete", capture_prompt)
        response = client.post(
            "/agent/chat",
            json={
                "message": "Summarize my note",
                "history": [],
                "attachment_ids": [local_attachment["attachment_id"]],
            },
        )
        assert response.status_code == 200
        assert "important launch detail" in captured["prompt"]

        created = client.post(
            "/pairing/sessions",
            json={"api_base_url": "http://127.0.0.1:8000"},
        )
        payload = compact_pairing_payload(created.json()["qr_payload"])
        claimed = client.post(
            "/pairing/claim",
            json={
                "pairing_id": payload["pairing_id"],
                "code": payload["code"],
                "device_name": "Pixel attachment test",
            },
        )
        token = claimed.json()["device_token"]
        authorization = {"Authorization": f"Bearer {token}"}
        mobile_upload = client.post(
            "/mobile/attachments",
            headers=authorization,
            files={"file": ("chart.png", b"\x89PNG\r\n", "image/png")},
        )
        assert mobile_upload.status_code == 201
        assert mobile_upload.json()["kind"] == "IMAGE"
        assert len(client.get("/mobile/attachments", headers=authorization).json()) == 1

        cross_owner = client.post(
            "/mobile/chat",
            headers=authorization,
            json={
                "message": "Read the laptop file",
                "history": [],
                "attachment_ids": [local_attachment["attachment_id"]],
            },
        )
        assert cross_owner.status_code == 404
