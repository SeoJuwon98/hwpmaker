from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "HWP Maker API"
    api_prefix: str = "/api"
    host: str = "0.0.0.0"
    port: int = 8100
    frontend_origin: str = "http://localhost:3100"

    storage_dir: str = "storage/generated"
    file_ttl_seconds: int = 60 * 30

    vllm_base_url: str = "http://localhost:8101/v1"
    vllm_model: str = "qwen3.5-35b-a3b-fp8"
    vllm_api_key: str = "EMPTY"
    vllm_max_tokens: int = 8192
    vllm_timeout_seconds: float = 180.0
    vllm_enable_thinking: bool = False
    vllm_reasoning_effort: str = "low"

    @property
    def backend_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def storage_path(self) -> Path:
        return self.backend_root / self.storage_dir


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
