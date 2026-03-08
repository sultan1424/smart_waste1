from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL:       str
    SYNC_DATABASE_URL:  str
    JWT_SECRET:         str = "dev-secret-change-in-production"
    JWT_EXPIRE_MINUTES: int = 60
    AES_256_KEY:        str = ""   # base64-encoded 32-byte key

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()