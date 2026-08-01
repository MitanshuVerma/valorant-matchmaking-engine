from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    redis_host: str = "localhost"
    redis_port: int = 6379
    
    postgres_url: str = "postgresql+asyncpg://riot:riotpass@localhost:5432/matchmaking"
    
    riot_api_key: str = ""
    trn_api_key: str = ""
    henrik_api_key: str = ""
    
    lobby_size: int = 10
    max_mmr_gap: float = 150.0
    mmr_expansion_rate: float = 25.0
    mmr_expansion_interval_sec: int = 5

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
