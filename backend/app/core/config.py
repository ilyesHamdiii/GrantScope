from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = (
        "postgresql+psycopg://grantscope:change-me-local-only@db:5432/grantscope"
    )
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024

    PUBLIC_DEMO_MODE: bool = False
    DEMO_SEED_BUNDLE_PATH: str = "/app/sample-data/demo-tenant.zip"
    DEMO_SEED_SOURCE_NAME: str = "public-demo-northbridge.zip"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()