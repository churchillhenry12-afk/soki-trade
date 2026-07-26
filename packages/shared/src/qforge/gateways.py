from __future__ import annotations

import json
from dataclasses import dataclass
from os import chmod
from pathlib import Path
from typing import Any, Literal, cast

import httpx

MT5Transport = Literal["rest", "mcp"]
MT5AccountMode = Literal["DEMO", "REAL"]


class GatewayConnectionError(RuntimeError):
    """A secret-safe failure raised when a remote gateway cannot be verified."""


@dataclass(frozen=True)
class TelegramConnection:
    token: str
    chat_id: str = ""


@dataclass(frozen=True)
class MT5Connection:
    transport: MT5Transport
    endpoint: str
    account_mode: MT5AccountMode
    token: str = ""


class GatewayManager:
    """Secret-safe configuration and real connectivity checks for external gateways."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.payload = self._load()

    def status(self) -> dict[str, dict[str, str | bool]]:
        telegram = cast(dict[str, Any], self.payload.get("telegram", {}))
        mt5 = cast(dict[str, Any], self.payload.get("mt5", {}))
        return {
            "telegram": {
                "configured": bool(telegram.get("token")),
                "connected": bool(telegram.get("connected")),
                "inbound_ready": bool(telegram.get("connected") and telegram.get("chat_id")),
                "bot_username": str(telegram.get("bot_username", "")),
                "chat_id_present": bool(telegram.get("chat_id")),
                "last_error": str(telegram.get("last_error", "")),
            },
            "mt5": {
                "configured": bool(mt5.get("endpoint")),
                "connected": bool(mt5.get("connected")),
                "transport": str(mt5.get("transport", "rest")),
                "endpoint": str(mt5.get("endpoint", "")),
                "account_mode": str(mt5.get("account_mode", "UNKNOWN")),
                "account_mode_source": str(
                    mt5.get("account_mode_source", "UNVERIFIED")
                ),
                "read_only": bool(mt5.get("read_only", True)),
                "last_error": str(mt5.get("last_error", "")),
            },
        }

    def telegram_connection(self) -> TelegramConnection | None:
        telegram = cast(dict[str, Any], self.payload.get("telegram", {}))
        token = str(telegram.get("token", ""))
        chat_id = str(telegram.get("chat_id", ""))
        if not telegram.get("connected") or not token or not chat_id:
            return None
        return TelegramConnection(token=token, chat_id=chat_id)

    def disconnect_telegram(self) -> dict[str, str | bool]:
        self.payload.pop("telegram", None)
        self._save()
        return self.status()["telegram"]

    def disconnect_mt5(self) -> dict[str, str | bool]:
        self.payload.pop("mt5", None)
        self._save()
        return self.status()["mt5"]

    async def connect_telegram(self, connection: TelegramConnection) -> dict[str, str | bool]:
        if not connection.token.strip():
            raise ValueError("Telegram bot token is required")
        base_url = f"https://api.telegram.org/bot{connection.token.strip()}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(f"{base_url}/getMe")
                response.raise_for_status()
                body = response.json()
                if not body.get("ok"):
                    raise ValueError("Telegram rejected the bot token")
                bot = cast(dict[str, Any], body.get("result", {}))
                if connection.chat_id.strip():
                    test = await client.post(
                        f"{base_url}/sendMessage",
                        json={
                            "chat_id": connection.chat_id.strip(),
                            "text": (
                                "Soki Trade is connected. Your agent is ready; "
                                "live trading remains disabled."
                            ),
                        },
                    )
                    test.raise_for_status()
        except httpx.HTTPStatusError as error:
            safe_error = f"Telegram returned HTTP {error.response.status_code}"
            self.payload["telegram"] = {
                "token": "",
                "chat_id": connection.chat_id.strip(),
                "connected": False,
                "last_error": safe_error,
            }
            self._save()
            raise GatewayConnectionError(safe_error) from error
        except httpx.HTTPError as error:
            safe_error = f"Telegram network check failed ({type(error).__name__})"
            self.payload["telegram"] = {
                "token": "",
                "chat_id": connection.chat_id.strip(),
                "connected": False,
                "last_error": safe_error,
            }
            self._save()
            raise GatewayConnectionError(safe_error) from error
        except ValueError as error:
            safe_error = str(error)
            self.payload["telegram"] = {
                "token": "",
                "chat_id": connection.chat_id.strip(),
                "connected": False,
                "last_error": safe_error,
            }
            self._save()
            raise GatewayConnectionError(safe_error) from error
        self.payload["telegram"] = {
            "token": connection.token.strip(),
            "chat_id": connection.chat_id.strip(),
            "connected": True,
            "bot_username": str(bot.get("username", "")),
            "last_error": "",
        }
        self._save()
        return self.status()["telegram"]

    async def connect_mt5(self, connection: MT5Connection) -> dict[str, str | bool]:
        endpoint = connection.endpoint.strip().rstrip("/")
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("MT5 gateway URL must start with http:// or https://")
        selected_mode = str(connection.account_mode).strip().upper()
        if selected_mode not in {"DEMO", "REAL"}:
            raise ValueError("Select whether the MT5 account is DEMO or REAL")
        headers = {"authorization": f"Bearer {connection.token}"} if connection.token else {}
        try:
            async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
                if connection.transport == "mcp":
                    response = await client.post(
                        endpoint,
                        headers={
                            **headers,
                            "accept": "application/json, text/event-stream",
                            "content-type": "application/json",
                        },
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "initialize",
                            "params": {
                                "protocolVersion": "2025-03-26",
                                "capabilities": {},
                                "clientInfo": {"name": "qforge", "version": "0.1.0"},
                            },
                        },
                    )
                else:
                    response = await client.get(f"{endpoint}/health", headers=headers)
                response.raise_for_status()
                body = self._response_object(response)
                reported_mode = self._reported_account_mode(body)
                if reported_mode in {"DEMO", "REAL"} and reported_mode != selected_mode:
                    raise ValueError(
                        f"MT5 bridge reports a {reported_mode} account, but {selected_mode} "
                        "was selected. Choose the matching account type and retry."
                    )
                account_mode = (
                    cast(MT5AccountMode, reported_mode)
                    if reported_mode in {"DEMO", "REAL"}
                    else cast(MT5AccountMode, selected_mode)
                )
                account_mode_source = (
                    "BRIDGE_VERIFIED"
                    if reported_mode in {"DEMO", "REAL"}
                    else "USER_SELECTED"
                )
        except httpx.HTTPError as error:
            safe_error = f"MT5 bridge network check failed ({type(error).__name__})"
            self.payload["mt5"] = {
                "transport": connection.transport,
                "endpoint": endpoint,
                "token": "",
                "connected": False,
                "account_mode": selected_mode,
                "account_mode_source": "UNVERIFIED",
                "read_only": True,
                "last_error": safe_error,
            }
            self._save()
            raise GatewayConnectionError(safe_error) from error
        except ValueError as error:
            safe_error = str(error)
            self.payload["mt5"] = {
                "transport": connection.transport,
                "endpoint": endpoint,
                "token": "",
                "connected": False,
                "account_mode": selected_mode,
                "account_mode_source": "UNVERIFIED",
                "read_only": True,
                "last_error": safe_error,
            }
            self._save()
            raise GatewayConnectionError(safe_error) from error
        self.payload["mt5"] = {
            "transport": connection.transport,
            "endpoint": endpoint,
            "token": connection.token,
            "connected": True,
            "account_mode": account_mode,
            "account_mode_source": account_mode_source,
            "read_only": True,
            "last_error": "",
        }
        self._save()
        return self.status()["mt5"]

    @staticmethod
    def _response_object(response: httpx.Response) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type:
            return {}
        body = response.json()
        return cast(dict[str, Any], body) if isinstance(body, dict) else {}

    @classmethod
    def _reported_account_mode(cls, body: dict[str, Any]) -> str:
        result = body.get("result")
        result_object = cast(dict[str, Any], result) if isinstance(result, dict) else {}
        candidates: list[Any] = [
            body.get("account_mode"),
            body.get("mode"),
            body.get("trade_mode"),
            result_object.get("account_mode"),
            result_object.get("mode"),
            result_object.get("trade_mode"),
        ]
        for container in (
            body.get("account"),
            body.get("account_info"),
            result_object.get("account"),
            result_object.get("account_info"),
        ):
            if isinstance(container, dict):
                candidates.extend(
                    (
                        container.get("account_mode"),
                        container.get("mode"),
                        container.get("trade_mode"),
                    )
                )
        for value in candidates:
            normalized = cls._normalize_account_mode(value)
            if normalized != "UNKNOWN":
                return normalized
        return "UNKNOWN"

    @staticmethod
    def _normalize_account_mode(value: Any) -> str:
        if isinstance(value, bool) or value is None:
            return "UNKNOWN"
        normalized = str(value).strip().upper()
        if normalized in {"0", "DEMO", "PAPER"}:
            return "DEMO"
        if normalized in {"2", "REAL", "LIVE"}:
            return "REAL"
        return "UNKNOWN"

    def _load(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        try:
            body = json.loads(self.config_path.read_text(encoding="utf-8"))
            return cast(dict[str, Any], body) if isinstance(body, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        chmod(self.config_path.parent, 0o700)
        self.config_path.touch(exist_ok=True, mode=0o600)
        chmod(self.config_path, 0o600)
        self.config_path.write_text(json.dumps(self.payload, indent=2), encoding="utf-8")
        chmod(self.config_path, 0o600)
