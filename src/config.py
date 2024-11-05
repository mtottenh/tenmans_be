from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET: str
    JWT_ALGORITHM: str
    API_VERSION: str
    ZENROWS_API_KEY: str
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


Config = Settings()
