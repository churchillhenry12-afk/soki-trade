from __future__ import annotations

import argparse
import json
from getpass import getpass
from typing import Any, cast

import httpx


def _request(
    client: httpx.Client, method: str, path: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    response = client.request(method, path, json=body)
    try:
        payload = response.json()
    except ValueError:
        payload = {"detail": response.text}
    if not response.is_success:
        detail = payload.get("detail", response.reason_phrase)
        raise SystemExit(f"Connection failed ({response.status_code}): {detail}")
    return cast(dict[str, Any], payload)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qforge-agent",
        description="Set up and talk to the local Soki Trade agent.",
    )
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="Soki Trade API URL")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Show every agent connection")

    model = commands.add_parser("connect-model", help="Connect and test a model gateway")
    model.add_argument(
        "--provider",
        choices=("local", "openai_compatible", "anthropic"),
        default="local",
    )
    model.add_argument("--model", required=True)
    model.add_argument("--url", required=True)
    model.add_argument("--api-key", action="store_true", help="Prompt securely for an API key")

    telegram = commands.add_parser("connect-telegram", help="Connect a Telegram bot")
    telegram.add_argument("--chat-id", default="")
    commands.add_parser("disconnect-telegram", help="Disconnect and forget the Telegram bot")

    mt5 = commands.add_parser("connect-mt5", help="Connect an MT5 REST bridge or MCP server")
    mt5.add_argument("--transport", choices=("rest", "mcp"), default="rest")
    mt5.add_argument("--url", required=True)
    mt5.add_argument("--token", action="store_true", help="Prompt securely for a gateway token")
    commands.add_parser("disconnect-mt5", help="Disconnect and forget the MT5 gateway")

    chat = commands.add_parser("chat", help="Send one message to the agent")
    chat.add_argument("message")
    chat.add_argument("--experiment-id")
    return parser


def main() -> None:
    args = _parser().parse_args()
    with httpx.Client(base_url=args.api.rstrip("/"), timeout=90) as client:
        if args.command == "status":
            payload = _request(client, "GET", "/setup/status")
        elif args.command == "connect-model":
            key = getpass("Model API key: ") if args.api_key else None
            _request(
                client,
                "POST",
                "/models/config",
                {
                    "provider": args.provider,
                    "model": args.model,
                    "base_url": args.url,
                    "api_key": key,
                    "persist": True,
                },
            )
            payload = _request(client, "POST", "/models/test")
        elif args.command == "connect-telegram":
            payload = _request(
                client,
                "POST",
                "/gateways/telegram/connect",
                {
                    "bot_token": getpass("Telegram bot token: "),
                    "chat_id": args.chat_id,
                },
            )
        elif args.command == "disconnect-telegram":
            payload = _request(client, "DELETE", "/gateways/telegram")
        elif args.command == "connect-mt5":
            token = getpass("MT5 gateway token: ") if args.token else None
            payload = _request(
                client,
                "POST",
                "/gateways/mt5/connect",
                {
                    "transport": args.transport,
                    "endpoint": args.url,
                    "token": token,
                },
            )
        elif args.command == "disconnect-mt5":
            payload = _request(client, "DELETE", "/gateways/mt5")
        else:
            payload = _request(
                client,
                "POST",
                "/agent/chat",
                {
                    "message": args.message,
                    "history": [],
                    "experiment_id": args.experiment_id,
                },
            )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
