from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Project Monitor API"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/project_monitor"
    queue_poll_interval_seconds: int = 5

    cors_origins: str = "https://logiq.thetechvoyager.in,http://localhost:8001"

    slack_webhook_url: str | None = None
    teams_webhook_url: str | None = None
    alert_email_from: str | None = None
    alert_email_to: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None

    llm_enabled: bool = False
    llm_provider: str = "ollama"
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""
    llm_timeout_seconds: int = 20
    llm_max_logs: int = 25
    llm_max_chars_per_log: int = 400
    llm_temperature: float = 0.1

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b-q4_K_M"
    ollama_timeout_seconds: int = 20
    ollama_max_logs: int = 25
    ollama_max_chars_per_log: int = 400
    ollama_temperature: float = 0.1

    @property
    def resolved_llm_base_url(self) -> str:
        return (self.llm_base_url or self.ollama_base_url).rstrip("/")

    @property
    def resolved_llm_model(self) -> str:
        return self.llm_model or self.ollama_model

    @property
    def resolved_llm_timeout_seconds(self) -> int:
        return self.llm_timeout_seconds or self.ollama_timeout_seconds

    @property
    def resolved_llm_max_logs(self) -> int:
        return self.llm_max_logs or self.ollama_max_logs

    @property
    def resolved_llm_max_chars_per_log(self) -> int:
        return self.llm_max_chars_per_log or self.ollama_max_chars_per_log

    @property
    def resolved_llm_temperature(self) -> float:
        return self.llm_temperature if self.llm_temperature is not None else self.ollama_temperature

    @property
    def resolved_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_llm_api_key(self) -> str | None:
        api_key = (self.llm_api_key or "").strip()
        if not api_key:
            return None
        return api_key

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
