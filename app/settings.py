"""Bootstrap config from .env. Most business knobs live in DB system_settings table."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    SECRET_KEY: str = "dev-only-change-me"
    ADMIN_EMAIL: str = ""

    DATABASE_URL: str = "sqlite:///./data/app.db"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM: str = "noreply@xpro.work"

    SIGNIN_POINTS: int = 10
    REQUEST_TIMEOUT_DAYS: int = 7
    CONFIRM_WINDOW_HOURS: int = 48
    MAX_PDF_SIZE_MB: int = 50
    MAX_ACTIVE_REQUESTS: int = 3
    SAME_JOURNAL_MONTHLY_LIMIT: int = 4
    REPORT_THRESHOLD: int = 3
    REPORTER_MIN_HELPS: int = 30
    PDF_DESENSITIZE_ENABLED: bool = True

    SITE_TITLE: str = "公益文献互助"
    SITE_SLOGAN: str = "输入标题、作者、年份，全社区帮你找全文"

    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 10800
    APP_BASE_PATH: str = "/preview/lit"
    DEBUG: bool = False


settings = Settings()
