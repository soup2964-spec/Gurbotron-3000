from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    fanvue_access_token: str = ""
    fanvue_creator_uuid: str = ""
    fanvue_api_url: str = "https://api.fanvue.com"
    fanvue_api_version: str = "2025-06-26"

    database_url: str = "sqlite:///./data/gurbotron.db"

    poll_interval_seconds: float = 45.0

    default_ppv_price_cents: int | None = None
    exit_messages_min: int = 20
    exit_messages_max: int = 30


settings = Settings()
