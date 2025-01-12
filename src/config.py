from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    JWT_SECRET: str
    JWT_ALGORITHM: str
    API_VERSION: str
    DB_ECHO: bool
    STEAM_API_KEY: str
    FRONTEND_URL: str
    REDIS_URL: str
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


Config = Settings()
