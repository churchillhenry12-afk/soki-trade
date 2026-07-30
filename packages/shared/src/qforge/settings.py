from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QFORGE_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/qforge.db"
    cors_origins: str = (
        "http://127.0.0.1:5173,http://localhost:5173,"
        "https://soki-trade-agent.vercel.app"
    )
    demo_mode: bool = False
    event_delay_ms: int = 0
    provider_config_path: str = "data/provider-config.json"
    gateway_config_path: str = "data/gateway-config.json"
    market_data_directory: str = "data/market"
    hermes_url: str = ""
    hermes_api_key: str = ""
    hermes_model: str = "hermes"
    hermes_timeout_seconds: float = 180
    hermes_config_path: str = "data/hermes-config.json"
    attachment_directory: str = "data/attachments"
    attachment_max_bytes: int = 200 * 1024 * 1024

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
