from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Auto Ledger"
    app_api_key: str = ""
    tz: str = "Asia/Shanghai"
    database_url: str = "sqlite:///./data/bookkeeping.db"

    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    wechat_token: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

