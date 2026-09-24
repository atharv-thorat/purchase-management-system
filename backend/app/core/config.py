"""Application settings, overridable with PMS_* environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PMS_", env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{BACKEND_DIR / 'pms.db'}"

    # Demo-only secret. Override with PMS_JWT_SECRET anywhere that isn't a laptop demo.
    jwt_secret: str = "dev-only-change-me-3b1f0c9e7a2d4e8f9c6b5a4d3e2f1a0b"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 8 * 60

    # "This month" for the budget check is the calendar month in this zone (SPEC assumptions).
    timezone: str = "Asia/Kolkata"

    # Exposes GET /api/auth/demo-users for the one-click login buttons.
    demo_mode: bool = True
    demo_password: str = "demo123"  # every seeded user's password

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


settings = Settings()
