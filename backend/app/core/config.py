from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Project Monitor API"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/project_monitor"
    queue_poll_interval_seconds: int = 5

    slack_webhook_url: str | None = None
    teams_webhook_url: str | None = None
    alert_email_from: str | None = None
    alert_email_to: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None

    llm_enabled: bool = True
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://192.168.1.34:11434"
    ollama_model: str = "qwen3:4b-q4_K_M"
    ollama_timeout_seconds: int = 20
    ollama_max_logs: int = 25
    ollama_max_chars_per_log: int = 400
    ollama_temperature: float = 0.5

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
