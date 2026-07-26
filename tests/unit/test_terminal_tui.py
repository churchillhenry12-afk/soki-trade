from pathlib import Path

from qforge_tui.main import (
    MAC_MT5_URL,
    SOKI_MARK,
    WINDOWS_MT5_URL,
    ModelScreen,
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
        assert "LIVE ORDERS OFF" in app.query_one("#connection-strip").render().plain
        app.set_working(True)
        assert app.query_one("#working-line").has_class("active")
        assert "SOKI" in app.query_one("#working-line").render().plain
        app.set_working(False)
        assert not app.query_one("#working-line").has_class("active")
        assert app.query_one("#working-line").render().plain == ""

        app.action_setup()
        await pilot.pause()
        assert isinstance(app.screen, SetupHub)
        assert app.screen.query_one("#hub-model").label.plain == "1  MODEL"

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
