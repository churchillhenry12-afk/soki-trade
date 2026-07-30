from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from time import monotonic, sleep
from typing import Any

import httpx
import uvicorn


def runtime_directory() -> Path:
    override = os.getenv("SOKI_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    local_app_data = os.getenv("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data) / "SokiTrade"
    return Path.home() / ".soki-trade"


def configure_runtime(directory: Path) -> None:
    data_directory = directory / "data"
    market_directory = data_directory / "market"
    market_directory.mkdir(parents=True, exist_ok=True)
    database_path = data_directory / "qforge.db"

    os.environ.setdefault("QFORGE_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    os.environ.setdefault(
        "QFORGE_PROVIDER_CONFIG_PATH",
        str(data_directory / "provider-config.json"),
    )
    os.environ.setdefault(
        "QFORGE_GATEWAY_CONFIG_PATH",
        str(data_directory / "gateway-config.json"),
    )
    os.environ.setdefault("QFORGE_MARKET_DATA_DIRECTORY", str(market_directory))
    os.environ.setdefault("QFORGE_DEMO_MODE", "false")
    os.chdir(directory)


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@dataclass
class EmbeddedApi:
    server: uvicorn.Server
    thread: Thread
    base_url: str

    @classmethod
    def start(cls, port: int, *, timeout: float = 30) -> EmbeddedApi:
        from qforge_api.main import app

        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        thread = Thread(target=server.run, name="soki-trade-api", daemon=True)
        embedded = cls(server=server, thread=thread, base_url=f"http://127.0.0.1:{port}")
        thread.start()
        embedded.wait_until_ready(timeout=timeout)
        return embedded

    def wait_until_ready(self, *, timeout: float) -> None:
        deadline = monotonic() + timeout
        last_error: Exception | None = None
        while monotonic() < deadline:
            if not self.thread.is_alive():
                raise RuntimeError("the embedded Soki Trade API stopped during startup")
            try:
                response = httpx.get(f"{self.base_url}/health", timeout=1)
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
                if payload.get("status") == "ok":
                    return
            except (httpx.HTTPError, ValueError) as error:
                last_error = error
            sleep(0.1)
        detail = f": {last_error}" if last_error is not None else ""
        raise TimeoutError(f"the embedded Soki Trade API did not start within {timeout:g}s{detail}")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)
        if self.thread.is_alive():
            self.server.force_exit = True
            self.thread.join(timeout=2)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Soki Trade Windows agent")
    parser.add_argument("--check", action="store_true", help="run a startup health check and exit")
    parser.add_argument("--port", type=int, default=0, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    directory = runtime_directory()
    directory.mkdir(parents=True, exist_ok=True)
    configure_runtime(directory)
    port = args.port or available_port()

    print("Starting Soki Trade...")
    api = EmbeddedApi.start(port)
    try:
        if args.check:
            from qforge_tui.main import check_api

            return asyncio.run(check_api(api.base_url))

        from qforge_tui.main import SokiTradeTerminal

        SokiTradeTerminal(api.base_url).run()
        return 0
    finally:
        api.stop()


def main() -> None:
    try:
        raise SystemExit(run())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as error:
        print(f"Soki Trade could not start: {error}", file=sys.stderr)
        raise SystemExit(1) from error
