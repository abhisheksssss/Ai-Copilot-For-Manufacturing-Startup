import os
from typing import Any
from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(_ENV_FILE_PATH)


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Manufacturing Copilot API"
    DEBUG: bool = True

    # API Keys
    GROQ_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_API_KEY_2: str | None = None
    NVIDIA_API_KEY: str | None = None
    NVIDIA_API_KEY_1: str | None = None
    NVIDIA_API_KEY_2: str | None = None
    NVIDIA_API_KEY_3: str | None = None
    GEMINI_API_KEY: str | None = None
    MISTRAL_API_KEY: str | None = None
    CEBREAS_API_KEY: str | None = None
    DATABASE_URL: str | None = None
    JWT_SECRET: str = "super-secret-key-that-is-at-least-32-bytes-long-for-hs256"

    @property
    def MISTRAL_KEY(self) -> str | None:
        return self.MISTRAL_API_KEY 

    @property
    def CEREBRAS_KEY(self) -> str | None:
        return self.CEBREAS_API_KEY

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "dev", "development"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
                return False

        return bool(value)

    model_config = SettingsConfigDict(env_file=_ENV_FILE_PATH, env_file_encoding="utf-8", extra="allow")


settings = Settings()
