from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class CLIConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    orchestrator_url: str = "http://localhost:8000"
    entra_tenant_id: str | None = None
    entra_app_client_id: str | None = None
    skip_auth: bool = False
    token_cache_path: Path = Path("~/.sre-agent/token_cache")


config = CLIConfig()  # type: ignore[call-arg]
