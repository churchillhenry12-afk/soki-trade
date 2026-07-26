from pathlib import Path

import qforge.executable as executable


def test_runtime_directory_prefers_explicit_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configured = tmp_path / "Soki Data"
    monkeypatch.setenv("SOKI_DATA_DIR", str(configured))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "ignored"))

    assert executable.runtime_directory() == configured.resolve()


def test_configure_runtime_uses_persistent_absolute_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path.parent)
    for name in (
        "QFORGE_DATABASE_URL",
        "QFORGE_PROVIDER_CONFIG_PATH",
        "QFORGE_GATEWAY_CONFIG_PATH",
        "QFORGE_MARKET_DATA_DIRECTORY",
        "QFORGE_DEMO_MODE",
    ):
        monkeypatch.delenv(name, raising=False)

    executable.configure_runtime(tmp_path)

    data_directory = tmp_path / "data"
    assert Path.cwd() == tmp_path
    assert executable.os.environ["QFORGE_DATABASE_URL"] == (
        f"sqlite:///{(data_directory / 'qforge.db').as_posix()}"
    )
    assert executable.os.environ["QFORGE_PROVIDER_CONFIG_PATH"] == str(
        data_directory / "provider-config.json"
    )
    assert executable.os.environ["QFORGE_GATEWAY_CONFIG_PATH"] == str(
        data_directory / "gateway-config.json"
    )
    assert executable.os.environ["QFORGE_MARKET_DATA_DIRECTORY"] == str(
        data_directory / "market"
    )
    assert executable.os.environ["QFORGE_DEMO_MODE"] == "false"
    assert (data_directory / "market").is_dir()


def test_available_port_returns_bindable_local_port() -> None:
    port = executable.available_port()

    assert 0 < port < 65536
