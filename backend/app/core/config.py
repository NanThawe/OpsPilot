from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str | None = None

    jwt_secret_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_classification_model: str = "gpt-5.4-nano"
    ai_provider: Literal["ollama", "openai"] = "ollama"
    ollama_model: str = "qwen3:4b-instruct"
    ollama_base_url: str = "http://127.0.0.1:11434"
    access_token_expire_minutes: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )
    document_storage_dir: Path = Path("data/private_documents")


settings = Settings()
