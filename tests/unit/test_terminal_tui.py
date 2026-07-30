from pathlib import Path

from qforge_tui.main import (
    MAC_MT5_URL,
    SOKI_MARK,
    WINDOWS_MT5_URL,
    HermesScreen,
    ModelScreen,
    PhonePairScreen,
    SetupHub,
    SokiTradeTerminal,
    available_path,
)
from textual.widgets import Button, Input, RichLog, Select


def test_mt5_downloads_use_official_metaquotes_cdn() -> None:
    assert MAC_MT5_URL.startswith("https://download.terminal.free/")
    assert WINDOWS_MT5_URL.startswith("https://download.terminal.free/")
    assert "www.metatrader5.com" in MAC_MT5_URL
    assert "www.metatrader5.com" in WINDOWS_MT5_URL


def test_available_path_does_not_overwrite_existing_file(tmp_path: Path) -> None:
    installer = tmp_path / "mt5setup.exe"
    installer.touch()

    assert available_path(installer) == tmp_path / "mt5setup-2.exe"


async def test_terminal_mounts_as_centered_single_conversation() -> None:
    app = SokiTradeTerminal("http://127.0.0.1:9")
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()

        mark = app.query_one("#soki-mark")
        assert SOKI_MARK in mark.render().plain
        assert app.query_one("#agent-input", Input).placeholder is not None
        assert app.query_one("#chat-log", RichLog).region.height >= 5
        assert "PAPER ONLY" in app.query_one("#connection-strip").render().plain
        app.set_working(True)
        activity = app.query_one("#activity-panel")
        assert activity.has_class("active")
        assert "work trace" in activity.render().plain
        app.update_activity(
            {
                "id": "runtime",
                "label": "Received the agent response",
                "state": "completed",
                "detail": "hermes",
            }
        )
        assert "Received the agent response" in activity.render().plain
        app.set_working(False)
        assert activity.has_class("active")

        app.action_setup()
        await pilot.pause()
        assert isinstance(app.screen, SetupHub)
        assert app.screen.query_one("#hub-hermes").label.plain == "HERMES RUNTIME"
        assert app.screen.query_one("#hub-model").label.plain == "FALLBACK MODEL"
        assert app.screen.query_one("#hub-phone").label.plain == "PAIR PHONE"
        assert len(app.screen.query("#hub-login")) == 0

        await pilot.press("escape")
        app.query_one("#agent-input", Input).value = "/help"
        app.submit_input()
        assert app.query_one("#agent-input", Input).value == ""


async def test_model_setup_scans_before_selecting_a_model() -> None:
    app = SokiTradeTerminal("http://127.0.0.1:9")
    async with app.run_test(size=(80, 24)) as pilot:
        app.push_screen(
            ModelScreen(
                app.api_url,
                {
                    "provider": "local",
                    "model": "qwen2.5-coder:14b",
                    "base_url": "http://127.0.0.1:11434/v1",
                },
            )
        )
        await pilot.pause()

        assert app.screen.query_one("#model-key", Input).password is True
        assert app.screen.query_one("#model-url", Input).value.endswith("/v1")
        assert isinstance(app.screen.query_one("#model-name"), Select)
        assert (
            app.screen.query_one("#model-scan", Button).label.plain
            == "SCAN AVAILABLE MODELS"
        )


async def test_hermes_setup_and_pairing_qr_are_first_class() -> None:
    app = SokiTradeTerminal("http://127.0.0.1:9")
    async with app.run_test(size=(80, 24)) as pilot:
        app.push_screen(
            HermesScreen(
                {
                    "url": "http://127.0.0.1:8642",
                    "model": "hermes-4",
                }
            )
        )
        await pilot.pause()

        assert app.screen.query_one("#hermes-url", Input).value.endswith(":8642")
        assert app.screen.query_one("#hermes-key", Input).password is True
        assert app.screen.query_one("#hermes-model", Input).value == "hermes-4"

        await pilot.press("escape")
        app.push_screen(
            PhonePairScreen(
                "soki:1:Ej5FZ-ibEtOkVkJmFBdAAA:abcdefghijklmnop",
                "soon",
            )
        )
        await pilot.pause()
        assert app.screen.query_one("#phone-qr").render().plain.strip()
        assert app.screen.query_one("#phone-pair").region.height <= 24
        assert app.screen.query_one("#phone-close").region.bottom <= 24
