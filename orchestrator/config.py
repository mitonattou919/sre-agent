from pydantic_settings import BaseSettings, SettingsConfigDict


class OrchestratorConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str
    mcp_server_url: str
    mcp_function_key: str | None = None

    entra_tenant_id: str | None = None
    entra_app_client_id: str | None = None
    skip_auth: bool = False


config = OrchestratorConfig()  # type: ignore[call-arg]
