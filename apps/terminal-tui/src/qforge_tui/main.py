from __future__ import annotations

import argparse
import asyncio
import json
import platform
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from os import chmod, getenv
from pathlib import Path
from typing import Any, ClassVar, Literal

import httpx
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Footer, Input, Label, RichLog, Select, Static

SOKI_MARK = r"""
███████╗ ██████╗ ██╗  ██╗██╗
██╔════╝██╔═══██╗██║ ██╔╝██║
███████╗██║   ██║█████╔╝ ██║
╚════██║██║   ██║██╔═██╗ ██║
███████║╚██████╔╝██║  ██╗██║
      S O K I  ·  T R A D E
""".strip("\n")

MAC_MT5_URL = (
    "https://download.terminal.free/cdn/web/metaquotes.ltd/mt5/"
    "MetaTrader5.pkg.zip?utm_campaign=download.mt5.macos&utm_source=www.metatrader5.com"
)
WINDOWS_MT5_URL = (
    "https://download.terminal.free/cdn/web/metaquotes.ltd/mt5/"
    "mt5setup.exe?utm_campaign=download&utm_source=www.metatrader5.com"
)
MT5_HELP_URL = "https://www.metatrader5.com/en/download"

PROVIDER_DEFAULTS = {
    "openai_compatible": ("", "https://api.openai.com/v1"),
    "anthropic": ("", "https://api.anthropic.com"),
    "local": ("qwen2.5-coder:14b", "http://127.0.0.1:11434/v1"),
}


@dataclass(frozen=True)
class ModelSubmission:
    provider: str
    model: str
    base_url: str
    api_key: str | None


@dataclass(frozen=True)
class TelegramSubmission:
    bot_token: str
    chat_id: str


@dataclass(frozen=True)
class MT5Submission:
    transport: Literal["rest", "mcp"]
    endpoint: str
    account_mode: Literal["DEMO", "REAL"]
    token: str | None


@dataclass(frozen=True)
class MT5LoginSubmission:
    login: str
    password: str
    server: str
    remember: bool


class SetupHub(ModalScreen[str | None]):
    CSS = """
    SetupHub {
        align: center middle;
        background: #020A0F 88%;
    }
    #setup-hub {
        width: 72;
        height: auto;
        padding: 2 3;
        border: round #45D9C1;
        background: #0B1F27;
    }
    #hub-title {
        height: 3;
        color: #DCEAE8;
        text-align: center;
        text-style: bold;
    }
    #hub-state {
        height: auto;
        margin-bottom: 1;
        padding: 1 2;
        background: #07131A;
        color: #72918C;
    }
    SetupHub Button {
        width: 1fr;
        margin: 0 1 1 0;
    }
    """
    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("escape", "close", "Close", show=False)
    ]

    def __init__(self, status: dict[str, Any]) -> None:
        super().__init__()
        self.status = status

    def compose(self) -> ComposeResult:
        model = self.status.get("model", {})
        telegram = self.status.get("telegram", {})
        mt5 = self.status.get("mt5", {})
        data = self.status.get("market_data", {})
        state = "\n".join(
            (
                f"MODEL      {'CONNECTED' if model.get('connected') else 'NOT CONNECTED'}"
                f"  ·  {model.get('model', '—')}",
                f"DATA       {data.get('status', '—')}  ·  {data.get('source', '—')}",
                f"TELEGRAM   {'CONNECTED' if telegram.get('inbound_ready') else 'NOT CONNECTED'}",
                f"MT5        {'CONNECTED' if mt5.get('connected') else 'NOT CONNECTED'}"
                f"  ·  {mt5.get('transport', '—')}",
            )
        )
        with Container(id="setup-hub"):
            yield Static("SOKI TRADE · CONNECTION SETUP", id="hub-title")
            yield Static(state, id="hub-state")
            with Horizontal():
                yield Button("1  MODEL", id="hub-model", variant="primary")
                yield Button("2  TELEGRAM", id="hub-telegram")
            with Horizontal():
                yield Button("3  MT5 GATEWAY", id="hub-mt5")
                yield Button("4  MT5 LOGIN", id="hub-login")
            with Horizontal():
                yield Button("INSTALL MT5", id="hub-install")
                yield Button("CLOSE", id="hub-close")

    @on(Button.Pressed)
    def choose(self, event: Button.Pressed) -> None:
        actions = {
            "hub-model": "model",
            "hub-telegram": "telegram",
            "hub-mt5": "mt5",
            "hub-login": "mt5-login",
            "hub-install": "install-mt5",
            "hub-close": None,
        }
        self.dismiss(actions.get(event.button.id or ""))

    def action_close(self) -> None:
        self.dismiss(None)


class FormScreen(ModalScreen[Any]):
    CSS = """
    FormScreen {
        align: center middle;
        background: #020A0F 88%;
    }
    .form-dialog {
        width: 78;
        height: auto;
        max-height: 92%;
        padding: 2 3;
        border: round #45D9C1;
        background: #0B1F27;
    }
    .form-title {
        height: 3;
        text-align: center;
        color: #DCEAE8;
        text-style: bold;
    }
    .form-help {
        height: auto;
        margin: 1 0;
        color: #72918C;
    }
    .form-fields {
        height: auto;
        max-height: 25;
        scrollbar-color: #45D9C1 #07131A;
    }
    FormScreen Label {
        color: #AFC8C4;
    }
    FormScreen Input, FormScreen Select {
        margin-bottom: 1;
        border: tall #294853;
        background: #07131A;
        color: #DCEAE8;
    }
    FormScreen Input:focus, FormScreen Select:focus {
        border: tall #45D9C1;
    }
    .form-actions {
        height: 3;
        margin-top: 1;
    }
    FormScreen Button {
        width: 1fr;
        margin-right: 1;
    }
    """
    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("escape", "cancel", "Cancel", show=False)
    ]

    def action_cancel(self) -> None:
        self.dismiss(None)


class ModelScreen(FormScreen):
    def __init__(self, api_url: str, current: dict[str, Any]) -> None:
        super().__init__()
        self.api_url = api_url
        self.current = current

    def compose(self) -> ComposeResult:
        provider = str(self.current.get("provider", "local"))
        if provider not in PROVIDER_DEFAULTS:
            provider = "local"
        current_model = str(self.current.get("model", "")).strip()
        model_options = ((current_model, current_model),) if current_model else ()
        with Container(classes="form-dialog"):
            yield Static("CONNECT AGENT INTELLIGENCE", classes="form-title")
            with VerticalScroll(classes="form-fields"):
                yield Label("Provider")
                yield Select(
                    (
                        ("Local Ollama / OpenAI-compatible", "local"),
                        ("OpenAI-compatible cloud", "openai_compatible"),
                        ("Anthropic", "anthropic"),
                    ),
                    value=provider,
                    allow_blank=False,
                    id="model-provider",
                )
                yield Label("API key")
                yield Input(
                    "",
                    password=True,
                    placeholder="Blank keeps the saved key; local Ollama needs none",
                    id="model-key",
                )
                yield Label("Base URL")
                yield Input(str(self.current.get("base_url", "")), id="model-url")
                yield Button("SCAN AVAILABLE MODELS", id="model-scan")
                yield Static(
                    "Enter the provider connection above, then scan its live model catalog.",
                    id="model-scan-status",
                    classes="form-help",
                )
                yield Label("Available model")
                yield Select(
                    model_options,
                    value=current_model or Select.BLANK,
                    allow_blank=True,
                    prompt="Scan provider to load models",
                    id="model-name",
                )
            yield Static(
                "After selection, Save performs a real model response test. Secrets stay "
                "in an owner-only local file and are never returned by the API.",
                classes="form-help",
            )
            with Horizontal(classes="form-actions"):
                yield Button("SAVE + TEST", id="model-save", variant="primary")
                yield Button("CANCEL", id="form-cancel")

    @on(Select.Changed, "#model-provider")
    def change_provider(self, event: Select.Changed) -> None:
        provider = str(event.value)
        if provider != self.current.get("provider"):
            model, url = PROVIDER_DEFAULTS[provider]
            self.query_one("#model-url", Input).value = url
            selector = self.query_one("#model-name", Select)
            selector.set_options(((model, model),) if model else ())
            selector.value = model or Select.BLANK
            self.query_one("#model-scan-status", Static).update(
                "Provider changed. Add its API key and base URL, then scan models."
            )

    @on(Button.Pressed, "#model-scan")
    def scan(self) -> None:
        self.scan_models()

    @work(exclusive=True, group="model-scan")
    async def scan_models(self) -> None:
        button = self.query_one("#model-scan", Button)
        status = self.query_one("#model-scan-status", Static)
        button.disabled = True
        button.label = "SCANNING PROVIDER…"
        status.update("Contacting the provider model catalog…")
        try:
            key = self.query_one("#model-key", Input).value.strip()
            async with httpx.AsyncClient(timeout=35) as client:
                response = await client.post(
                    f"{self.api_url}/models/scan",
                    json={
                        "provider": str(self.query_one("#model-provider", Select).value),
                        "base_url": self.query_one("#model-url", Input).value.strip(),
                        "api_key": key or None,
                    },
                )
                response.raise_for_status()
            models = [str(model) for model in response.json()["models"]]
            selector = self.query_one("#model-name", Select)
            selector.set_options((model, model) for model in models)
            current_model = str(self.current.get("model", ""))
            selector.value = current_model if current_model in models else models[0]
            status.update(f"Found {len(models)} models. Choose one below.")
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            status.update(f"Scan failed: {response_detail(error)}")
        finally:
            button.disabled = False
            button.label = "SCAN AVAILABLE MODELS"

    @on(Button.Pressed, "#model-save")
    def save(self) -> None:
        key = self.query_one("#model-key", Input).value.strip()
        selected_model = self.query_one("#model-name", Select).value
        if selected_model is Select.BLANK or not str(selected_model).strip():
            self.query_one("#model-scan-status", Static).update(
                "Scan the provider and choose a model before saving."
            )
            return
        self.dismiss(
            ModelSubmission(
                provider=str(self.query_one("#model-provider", Select).value),
                model=str(selected_model).strip(),
                base_url=self.query_one("#model-url", Input).value.strip(),
                api_key=key or None,
            )
        )

    @on(Button.Pressed, "#form-cancel")
    def cancel(self) -> None:
        self.dismiss(None)


class TelegramScreen(FormScreen):
    def compose(self) -> ComposeResult:
        with Container(classes="form-dialog"):
            yield Static("CONNECT TELEGRAM", classes="form-title")
            yield Label("Bot token")
            yield Input("", password=True, placeholder="Token from @BotFather", id="tg-token")
            yield Label("Your Telegram chat ID")
            yield Input(
                "",
                placeholder="Only this chat will be allowed to control the agent",
                id="tg-chat",
            )
            yield Static(
                "Soki Trade validates the bot with Telegram, sends a real test message, "
                "and then listens only to the exact chat ID entered here.",
                classes="form-help",
            )
            with Horizontal(classes="form-actions"):
                yield Button("CONNECT + TEST", id="tg-save", variant="primary")
                yield Button("CANCEL", id="form-cancel")

    @on(Button.Pressed, "#tg-save")
    def save(self) -> None:
        self.dismiss(
            TelegramSubmission(
                bot_token=self.query_one("#tg-token", Input).value.strip(),
                chat_id=self.query_one("#tg-chat", Input).value.strip(),
            )
        )

    @on(Button.Pressed, "#form-cancel")
    def cancel(self) -> None:
        self.dismiss(None)


class MT5Screen(FormScreen):
    def __init__(self, current: dict[str, Any]) -> None:
        super().__init__()
        self.current = current

    def compose(self) -> ComposeResult:
        transport = str(self.current.get("transport", "mcp"))
        if transport not in {"rest", "mcp"}:
            transport = "mcp"
        account_mode = str(self.current.get("account_mode", "DEMO")).upper()
        if account_mode not in {"DEMO", "REAL"}:
            account_mode = "DEMO"
        with Container(classes="form-dialog"):
            yield Static("CONNECT MT5 GATEWAY", classes="form-title")
            yield Label("Account type")
            yield Select(
                (
                    ("Demo account", "DEMO"),
                    ("Real account · read-only", "REAL"),
                ),
                value=account_mode,
                allow_blank=False,
                id="mt5-account-mode",
            )
            yield Label("Transport")
            yield Select(
                (("Native MT5 / MCP", "mcp"), ("REST bridge", "rest")),
                value=transport,
                allow_blank=False,
                id="mt5-transport",
            )
            yield Label("Gateway URL")
            yield Input(
                str(self.current.get("endpoint", "")),
                placeholder="http://127.0.0.1:PORT/mcp",
                id="mt5-url",
            )
            yield Label("Gateway token")
            yield Input(
                "",
                password=True,
                placeholder="Blank if the local endpoint needs no token",
                id="mt5-token",
            )
            yield Static(
                "Connect performs a real MCP initialize or REST health check. If the bridge "
                "reports an account type, it must match your selection. Real accounts are "
                "read-only; live order execution remains disabled.",
                classes="form-help",
            )
            with Horizontal(classes="form-actions"):
                yield Button("CONNECT + VERIFY", id="mt5-save", variant="primary")
                yield Button("CANCEL", id="form-cancel")

    @on(Button.Pressed, "#mt5-save")
    def save(self) -> None:
        token = self.query_one("#mt5-token", Input).value.strip()
        self.dismiss(
            MT5Submission(
                transport=str(self.query_one("#mt5-transport", Select).value),  # type: ignore[arg-type]
                endpoint=self.query_one("#mt5-url", Input).value.strip(),
                account_mode=str(  # type: ignore[arg-type]
                    self.query_one("#mt5-account-mode", Select).value
                ),
                token=token or None,
            )
        )

    @on(Button.Pressed, "#form-cancel")
    def cancel(self) -> None:
        self.dismiss(None)


class MT5LoginScreen(FormScreen):
    def compose(self) -> ComposeResult:
        with Container(classes="form-dialog"):
            yield Static("LOGIN TO MT5 · DEMO / INVESTOR", classes="form-title")
            yield Label("Account login")
            yield Input("", placeholder="Account number", id="login-number")
            yield Label("Broker server")
            yield Input("", placeholder="Broker-Server or host:port", id="login-server")
            yield Label("Demo or investor password")
            yield Input("", password=True, id="login-password")
            yield Checkbox(
                "Ask MT5 to remember the account",
                value=True,
                id="login-remember",
            )
            yield Static(
                "The password is written to a temporary owner-only configuration, passed "
                "to the official MT5 terminal, then deleted. Automated trading is forced off. "
                "Passkey or broker confirmation may still appear in MT5.",
                classes="form-help",
            )
            with Horizontal(classes="form-actions"):
                yield Button("LAUNCH + LOGIN", id="login-save", variant="primary")
                yield Button("CANCEL", id="form-cancel")

    @on(Button.Pressed, "#login-save")
    def save(self) -> None:
        self.dismiss(
            MT5LoginSubmission(
                login=self.query_one("#login-number", Input).value.strip(),
                server=self.query_one("#login-server", Input).value.strip(),
                password=self.query_one("#login-password", Input).value,
                remember=self.query_one("#login-remember", Checkbox).value,
            )
        )

    @on(Button.Pressed, "#form-cancel")
    def cancel(self) -> None:
        self.dismiss(None)


class SokiTradeTerminal(App[None]):
    TITLE = "Soki Trade"
    SUB_TITLE = "Operations agent · trading intelligence"
    CSS = """
    Screen {
        align: center top;
        background: #020A0F;
        color: #DCEAE8;
    }
    #soki-shell {
        width: 112;
        max-width: 96%;
        height: 100%;
        padding: 0 2;
        background: #07131A;
    }
    #soki-mark {
        height: 6;
        color: #45D9C1;
        text-align: center;
        text-style: bold;
    }
    #connection-strip {
        height: 1;
        padding: 0 1;
        background: #0B1F27;
        color: #AFC8C4;
        text-align: center;
    }
    #chat-log {
        height: 1fr;
        min-height: 5;
        margin-top: 1;
        padding: 1 2;
        border: round #294853;
        background: #051016;
        scrollbar-color: #45D9C1 #07131A;
    }
    #working-line {
        height: 0;
        padding: 0 2;
        color: #8CE9D9;
        background: #0A1920;
        text-style: italic;
    }
    #working-line.active {
        height: 1;
    }
    #quick-line {
        height: 1;
        padding: 0 1;
        color: #72918C;
        text-align: center;
    }
    #composer {
        height: 3;
    }
    #agent-input {
        width: 1fr;
        margin-right: 1;
        border: tall #294853;
        background: #0B1F27;
        color: #DCEAE8;
    }
    #agent-input:focus {
        border: tall #45D9C1;
    }
    #send {
        width: 14;
        background: #45D9C1;
        color: #020A0F;
        text-style: bold;
    }
    #notice {
        height: 1;
        color: #65A7FF;
        text-align: center;
    }
    Footer {
        background: #07131A;
        color: #72918C;
    }
    Button {
        border: tall #294853;
        background: #0B1F27;
        color: #DCEAE8;
    }
    Button:hover, Button:focus {
        border: tall #45D9C1;
        color: #45D9C1;
    }
    Button.-primary {
        background: #45D9C1;
        color: #020A0F;
    }
    """
    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("ctrl+s", "setup", "Setup"),
        Binding("ctrl+l", "clear_chat", "Clear"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, api_url: str) -> None:
        super().__init__()
        self.api_url = api_url.rstrip("/")
        self.setup_status: dict[str, Any] = {}
        self.history: list[dict[str, str]] = []
        self.experiment_id: str | None = None

    def compose(self) -> ComposeResult:
        with Container(id="soki-shell"):
            yield Static(SOKI_MARK, id="soki-mark")
            yield Static(
                "AGENT ○   DATA ○   TELEGRAM ○   MT5 ○   LIVE ORDERS OFF",
                id="connection-strip",
            )
            yield RichLog(id="chat-log", highlight=False, markup=False, wrap=True)
            yield Static("", id="working-line")
            yield Static(
                "/connect telegram  /connect mt5  /backtest EURUSD M15  /help",
                id="quick-line",
            )
            with Horizontal(id="composer"):
                yield Input(
                    placeholder="Talk to Soki Trade… or type /help",
                    id="agent-input",
                )
                yield Button("SEND  ↵", id="send", variant="primary")
            yield Static("", id="notice")
        yield Footer()

    async def on_mount(self) -> None:
        self.query_one("#chat-log", RichLog).write(
            self._agent_text(
                "Online. I can handle general questions, manage your connections, and run "
                "trading research. Ask normally or type /help."
            )
        )
        await self.refresh_setup()
        self.query_one("#agent-input", Input).focus()

    @staticmethod
    def _agent_text(message: str) -> Text:
        line = Text()
        line.append("● SOKI  ", style="bold #45D9C1")
        line.append(message, style="#DCEAE8")
        return line

    @staticmethod
    def _user_text(message: str) -> Text:
        line = Text()
        line.append("  YOU   ", style="bold #65A7FF")
        line.append(message, style="#AFC8C4")
        return line

    @staticmethod
    def _system_text(message: str, *, warning: bool = False) -> Text:
        return Text(
            f"  {'!' if warning else '·'}     {message}",
            style="#E6B85C" if warning else "#72918C",
        )

    def set_notice(self, message: str) -> None:
        self.query_one("#notice", Static).update(message)

    def set_working(self, active: bool) -> None:
        indicator = self.query_one("#working-line", Static)
        indicator.update(
            "● SOKI  Working · understanding your request and checking tools…"
            if active
            else ""
        )
        indicator.set_class(active, "active")

    async def refresh_setup(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.get(f"{self.api_url}/setup/status")
                response.raise_for_status()
            self.setup_status = response.json()
            model = self.setup_status.get("model", {})
            telegram = self.setup_status.get("telegram", {})
            mt5 = self.setup_status.get("mt5", {})
            data = self.setup_status.get("market_data", {})
            self.query_one("#connection-strip", Static).update(
                "   ".join(
                    (
                        f"AGENT {'●' if model.get('connected') else '○'}",
                        f"DATA {'●' if data.get('status') == 'READY' else '○'}",
                        f"TELEGRAM {'●' if telegram.get('inbound_ready') else '○'}",
                        f"MT5 {'●' if mt5.get('connected') else '○'}",
                        "LIVE ORDERS OFF",
                    )
                )
            )
            self.set_notice("Ready · one terminal, one conversation")
        except (httpx.HTTPError, ValueError) as error:
            self.set_notice(f"Agent API unavailable · {type(error).__name__}")

    @on(Button.Pressed, "#send")
    def press_send(self) -> None:
        self.submit_input()

    @on(Input.Submitted, "#agent-input")
    def enter_send(self) -> None:
        self.submit_input()

    def submit_input(self) -> None:
        field = self.query_one("#agent-input", Input)
        message = field.value.strip()
        if not message:
            return
        field.value = ""
        self.query_one("#chat-log", RichLog).write(self._user_text(message))
        if message.startswith("/"):
            self.run_command(message)
        else:
            self.send_agent_message(message)

    def run_command(self, command_line: str) -> None:
        command, _, argument = command_line.partition(" ")
        command = command.lower()
        if command == "/setup":
            self.action_setup()
        elif command == "/connect":
            if argument.strip():
                self.send_agent_message(f"Connect {argument.strip()}")
            else:
                self.action_setup()
        elif command == "/disconnect":
            if argument.strip():
                self.send_agent_message(f"Disconnect {argument.strip()}")
            else:
                self.query_one("#chat-log", RichLog).write(
                    self._system_text(
                        "Choose a target: /disconnect telegram or /disconnect mt5.",
                        warning=True,
                    )
                )
        elif command == "/model":
            self.open_model()
        elif command == "/telegram":
            self.open_telegram()
        elif command == "/mt5":
            self.open_mt5()
        elif command == "/mt5-login":
            self.open_mt5_login()
        elif command == "/install-mt5":
            self.install_mt5()
        elif command == "/status":
            self.write_status()
        elif command in {"/backtest", "/test"}:
            request = argument.strip() or "EURUSD M15"
            self.send_agent_message(f"Backtest {request}")
        elif command in {"/report", "/results"}:
            self.send_agent_message("Show me the current report")
        elif command == "/clear":
            self.action_clear_chat()
        elif command in {"/quit", "/exit"}:
            self.exit()
        elif command == "/help":
            self.write_help()
        else:
            self.query_one("#chat-log", RichLog).write(
                self._system_text(f"Unknown command {command}. Type /help.", warning=True)
            )

    def write_help(self) -> None:
        help_text = (
            "QUICK COMMANDS\n"
            "  /setup                 all connections\n"
            "  /connect telegram      connect Telegram through chat\n"
            "  /connect mt5           connect MT5 through chat\n"
            "  /disconnect telegram   disconnect and forget Telegram\n"
            "  /disconnect mt5        disconnect and forget MT5\n"
            "  /model                 model provider and API key\n"
            "  /telegram              Telegram bot gateway\n"
            "  /mt5                   REST or native MCP gateway\n"
            "  /install-mt5           download official MT5 installer\n"
            "  /mt5-login             launch MT5 with demo/investor login\n"
            "  /backtest EURUSD M15   start a real-data study\n"
            "  /report                explain the current report\n"
            "  /status                show connection state\n"
            "  /clear · /quit         clear chat or exit\n"
            "\nTalk normally too: ask a general question, manage connections, or "
            "say “Test my EURUSD trend idea on H1.”"
        )
        self.query_one("#chat-log", RichLog).write(self._system_text(help_text))

    def write_status(self) -> None:
        model = self.setup_status.get("model", {})
        telegram = self.setup_status.get("telegram", {})
        mt5 = self.setup_status.get("mt5", {})
        data = self.setup_status.get("market_data", {})
        status = (
            f"Model: {'connected' if model.get('connected') else 'off'}"
            f" ({model.get('model', '—')}) · "
            f"Data: {data.get('status', '—')} ({data.get('source', '—')}) · "
            f"Telegram: {'connected' if telegram.get('inbound_ready') else 'off'} · "
            f"MT5: {'connected' if mt5.get('connected') else 'off'}"
        )
        self.query_one("#chat-log", RichLog).write(self._system_text(status))

    def action_setup(self) -> None:
        self.push_screen(SetupHub(self.setup_status), self.setup_choice)

    def setup_choice(self, choice: str | None) -> None:
        if choice == "model":
            self.open_model()
        elif choice == "telegram":
            self.open_telegram()
        elif choice == "mt5":
            self.open_mt5()
        elif choice == "mt5-login":
            self.open_mt5_login()
        elif choice == "install-mt5":
            self.install_mt5()

    def open_model(self) -> None:
        self.push_screen(
            ModelScreen(self.api_url, self.setup_status.get("model", {})),
            self.model_submitted,
        )

    def model_submitted(self, submission: ModelSubmission | None) -> None:
        if submission is not None:
            self.connect_model(submission)

    def open_telegram(self) -> None:
        self.push_screen(TelegramScreen(), self.telegram_submitted)

    def telegram_submitted(self, submission: TelegramSubmission | None) -> None:
        if submission is not None:
            self.connect_telegram(submission)

    def open_mt5(self) -> None:
        self.push_screen(
            MT5Screen(self.setup_status.get("mt5", {})),
            self.mt5_submitted,
        )

    def mt5_submitted(self, submission: MT5Submission | None) -> None:
        if submission is not None:
            self.connect_mt5(submission)

    def open_mt5_login(self) -> None:
        if not mt5_is_installed():
            self.query_one("#chat-log", RichLog).write(
                self._system_text(
                    "MT5 is not installed, so I am downloading the official installer now. "
                    "Finish installation, then run /mt5-login again."
                )
            )
            self.install_mt5()
            return
        self.push_screen(MT5LoginScreen(), self.mt5_login_submitted)

    def mt5_login_submitted(self, submission: MT5LoginSubmission | None) -> None:
        if submission is not None:
            self.launch_mt5_login(submission)

    def action_clear_chat(self) -> None:
        self.query_one("#chat-log", RichLog).clear()
        self.query_one("#chat-log", RichLog).write(
            self._agent_text("Fresh conversation. What can I take care of?")
        )
        self.history.clear()

    @work(exclusive=True, group="agent-chat")
    async def send_agent_message(self, message: str) -> None:
        field = self.query_one("#agent-input", Input)
        field.disabled = True
        self.set_working(True)
        self.set_notice("Request in progress")
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.post(
                    f"{self.api_url}/agent/chat",
                    json={
                        "message": message,
                        "history": self.history[-20:],
                        "experiment_id": self.experiment_id,
                    },
                )
                response.raise_for_status()
            body = response.json()
            reply = str(body["reply"])
            if body.get("experiment_id"):
                self.experiment_id = str(body["experiment_id"])
            self.query_one("#chat-log", RichLog).write(self._agent_text(reply))
            self.history.extend(
                (
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": reply},
                )
            )
            action = str(body.get("action", "MESSAGE")).replace("_", " ").lower()
            if body.get("action") == "CONNECTION_CHANGED":
                await self.refresh_setup()
            client_action = body.get("client_action")
            if client_action == "CONNECT_MODEL":
                self.call_after_refresh(self.open_model)
            elif client_action == "CONNECT_TELEGRAM":
                self.call_after_refresh(self.open_telegram)
            elif client_action == "CONNECT_MT5":
                self.call_after_refresh(self.open_mt5)
            self.set_notice(f"Ready · {action}")
        except (httpx.HTTPError, KeyError, ValueError) as error:
            detail = response_detail(error)
            self.query_one("#chat-log", RichLog).write(
                self._system_text(f"Request failed: {detail}", warning=True)
            )
            self.set_notice("Request failed · check /status")
        finally:
            self.set_working(False)
            field.disabled = False
            field.focus()

    @work(exclusive=True, group="model")
    async def connect_model(self, submission: ModelSubmission) -> None:
        self.set_notice("Testing model connection…")
        try:
            async with httpx.AsyncClient(timeout=75) as client:
                configured = await client.post(
                    f"{self.api_url}/models/config",
                    json={
                        "provider": submission.provider,
                        "model": submission.model,
                        "base_url": submission.base_url,
                        "api_key": submission.api_key,
                        "persist": True,
                    },
                )
                configured.raise_for_status()
                tested = await client.post(f"{self.api_url}/models/test")
                tested.raise_for_status()
            self.query_one("#chat-log", RichLog).write(
                self._system_text(f"Model connected: {submission.model}")
            )
            await self.refresh_setup()
        except httpx.HTTPError as error:
            self.query_one("#chat-log", RichLog).write(
                self._system_text(
                    f"Model connection failed: {response_detail(error)}",
                    warning=True,
                )
            )

    @work(exclusive=True, group="telegram")
    async def connect_telegram(self, submission: TelegramSubmission) -> None:
        self.set_notice("Contacting Telegram…")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.api_url}/gateways/telegram/connect",
                    json={
                        "bot_token": submission.bot_token,
                        "chat_id": submission.chat_id,
                    },
                )
                response.raise_for_status()
            self.query_one("#chat-log", RichLog).write(
                self._system_text("Telegram connected and test message delivered.")
            )
            await self.refresh_setup()
        except httpx.HTTPError as error:
            self.query_one("#chat-log", RichLog).write(
                self._system_text(
                    f"Telegram connection failed: {response_detail(error)}",
                    warning=True,
                )
            )

    @work(exclusive=True, group="mt5")
    async def connect_mt5(self, submission: MT5Submission) -> None:
        self.set_notice("Verifying MT5 gateway…")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.api_url}/gateways/mt5/connect",
                    json={
                        "transport": submission.transport,
                        "endpoint": submission.endpoint,
                        "account_mode": submission.account_mode,
                        "token": submission.token,
                    },
                )
                response.raise_for_status()
            self.query_one("#chat-log", RichLog).write(
                self._system_text(
                    f"MT5 {submission.account_mode} account connected through "
                    f"{submission.transport.upper()} in read-only mode."
                )
            )
            await self.refresh_setup()
        except httpx.HTTPError as error:
            self.query_one("#chat-log", RichLog).write(
                self._system_text(
                    f"MT5 connection failed: {response_detail(error)}", warning=True
                )
            )

    @work(exclusive=True, group="mt5-install")
    async def install_mt5(self) -> None:
        if mt5_is_installed():
            self.query_one("#chat-log", RichLog).write(
                self._system_text("MetaTrader 5 is already installed.")
            )
            return
        self.set_notice("Downloading the official MT5 installer…")
        try:
            installer = await download_mt5_installer()
            open_path(installer)
            self.query_one("#chat-log", RichLog).write(
                self._system_text(
                    f"Official installer downloaded to {installer}. "
                    "Finish the signed installer, then return and run /mt5-login."
                )
            )
            self.set_notice("MT5 installer opened")
        except (httpx.HTTPError, OSError, ValueError, zipfile.BadZipFile) as error:
            self.query_one("#chat-log", RichLog).write(
                self._system_text(f"MT5 install failed: {error}", warning=True)
            )
            self.set_notice("MT5 install failed")

    @work(exclusive=True, group="mt5-login")
    async def launch_mt5_login(self, submission: MT5LoginSubmission) -> None:
        if not submission.login or not submission.password or not submission.server:
            self.query_one("#chat-log", RichLog).write(
                self._system_text("Login, password, and broker server are required.", warning=True)
            )
            return
        self.set_notice("Launching the official MT5 terminal…")
        config_path = Path("data/mt5-login.ini").resolve()
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            config_path.touch(exist_ok=True, mode=0o600)
            chmod(config_path, 0o600)
            config_path.write_text(
                "\n".join(
                    (
                        "[Common]",
                        f"Login={submission.login}",
                        f"Server={submission.server}",
                        f"Password={submission.password}",
                        f"KeepPrivate={1 if submission.remember else 0}",
                        "",
                        "[Experts]",
                        "AllowLiveTrading=0",
                        "Enabled=0",
                    )
                ),
                encoding="utf-8",
            )
            chmod(config_path, 0o600)
            launch_mt5_with_config(config_path)
            self.query_one("#chat-log", RichLog).write(
                self._system_text(
                    "MT5 launched with the requested account. Automated trading is off. "
                    "Complete any broker or passkey prompt in MT5."
                )
            )
            self.set_notice("MT5 login launched")
            await asyncio.sleep(45)
        except OSError as error:
            self.query_one("#chat-log", RichLog).write(
                self._system_text(f"Could not launch MT5: {error}", warning=True)
            )
        finally:
            config_path.unlink(missing_ok=True)


def response_detail(error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        try:
            payload = error.response.json()
            detail = payload.get("detail", error.response.reason_phrase)
            return json.dumps(detail) if isinstance(detail, (dict, list)) else str(detail)
        except ValueError:
            return error.response.reason_phrase
    return str(error)


def mt5_is_installed() -> bool:
    system = platform.system()
    if system == "Darwin":
        return any(
            path.exists()
            for path in (
                Path("/Applications/MetaTrader 5.app"),
                Path.home() / "Applications/MetaTrader 5.app",
                Path.home()
                / "Library/Application Support/net.metaquotes.wine.metatrader5/"
                "drive_c/Program Files/MetaTrader 5/terminal64.exe",
            )
        )
    if system == "Windows":
        return mt5_windows_executable() is not None
    return shutil.which("wine") is not None and mt5_wine_executable() is not None


def mt5_windows_executable() -> Path | None:
    roots = [getenv("PROGRAMFILES", ""), getenv("PROGRAMFILES(X86)", "")]
    for root in roots:
        if root:
            candidate = Path(root) / "MetaTrader 5/terminal64.exe"
            if candidate.exists():
                return candidate
    return None


def mt5_wine_executable() -> Path | None:
    candidates = (
        Path.home() / ".mt5/drive_c/Program Files/MetaTrader 5/terminal64.exe",
        Path.home()
        / "Library/Application Support/net.metaquotes.wine.metatrader5/"
        "drive_c/Program Files/MetaTrader 5/terminal64.exe",
    )
    return next((candidate for candidate in candidates if candidate.exists()), None)


async def download_mt5_installer() -> Path:
    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    system = platform.system()
    if system == "Darwin":
        archive = available_path(downloads / "MetaTrader5.pkg.zip")
        async with (
            httpx.AsyncClient(timeout=180, follow_redirects=True) as client,
            client.stream("GET", MAC_MT5_URL) as response,
        ):
            response.raise_for_status()
            with archive.open("wb") as output:
                async for chunk in response.aiter_bytes():
                    output.write(chunk)
        extract_to = available_path(downloads / "SokiTrade-MT5-Installer")
        extract_to.mkdir()
        with zipfile.ZipFile(archive) as package:
            root = extract_to.resolve()
            for member in package.infolist():
                destination = (root / member.filename).resolve()
                if not destination.is_relative_to(root):
                    raise ValueError("the official archive contained an unsafe path")
            package.extractall(extract_to)
        installers = list(extract_to.rglob("*.pkg"))
        if not installers:
            raise ValueError("the official archive did not contain a macOS package")
        return installers[0]
    if system == "Windows":
        installer = available_path(downloads / "mt5setup.exe")
        async with (
            httpx.AsyncClient(timeout=180, follow_redirects=True) as client,
            client.stream("GET", WINDOWS_MT5_URL) as response,
        ):
            response.raise_for_status()
            with installer.open("wb") as output:
                async for chunk in response.aiter_bytes():
                    output.write(chunk)
        return installer
    open_path(MT5_HELP_URL)
    raise ValueError("the official Linux installation guide was opened")


def available_path(path: Path) -> Path:
    if not path.exists():
        return path
    for number in range(2, 1000):
        candidate = path.with_name(f"{path.stem}-{number}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise OSError(f"could not reserve a safe download name beside {path.name}")


def open_path(target: str | Path) -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", str(target)])
    elif system == "Windows":
        subprocess.Popen(["cmd", "/c", "start", "", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


def launch_mt5_with_config(config_path: Path) -> None:
    system = platform.system()
    if system == "Windows":
        executable = mt5_windows_executable()
        if executable is None:
            raise OSError("MetaTrader 5 executable was not found")
        subprocess.Popen([str(executable), f"/config:{config_path}"])
        return
    windows_path = "Z:" + str(config_path).replace("/", "\\")
    if system == "Darwin":
        application = Path("/Applications/MetaTrader 5.app")
        if not application.exists():
            application = Path.home() / "Applications/MetaTrader 5.app"
        if application.exists():
            subprocess.Popen(
                ["open", "-a", str(application), "--args", f"/config:{windows_path}"]
            )
            return
    executable = mt5_wine_executable()
    wine = shutil.which("wine64") or shutil.which("wine")
    if executable is None or wine is None:
        raise OSError("MT5 or its Wine runner was not found")
    subprocess.Popen([wine, str(executable), f"/config:{windows_path}"])


async def check_api(api_url: str) -> int:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{api_url.rstrip('/')}/setup/status")
            response.raise_for_status()
        status = response.json()
    except (httpx.HTTPError, KeyError) as error:
        print(f"Soki Trade terminal check failed: {error}")
        return 1
    print(
        "Soki Trade ready | "
        f"agent={status['agent']['ready']} | "
        f"model={status['model']['connected']} | "
        f"data={status['market_data']['status']} | "
        f"telegram={status['telegram']['inbound_ready']} | "
        f"mt5={status['mt5']['connected']}"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Soki Trade native agent terminal")
    parser.add_argument(
        "--api-url",
        default=getenv("QFORGE_API_URL", "http://127.0.0.1:8000"),
        help="Soki Trade API base URL",
    )
    parser.add_argument("--check", action="store_true", help="verify terminal connectivity")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.check:
        raise SystemExit(asyncio.run(check_api(args.api_url)))
    SokiTradeTerminal(args.api_url).run()


if __name__ == "__main__":
    main()
