from pydantic import BaseModel
from typing import Optional

class PlayerTelemetryResponse(BaseModel):
    puuid: str
    game_name: str
    tag_line: str
    match_count: int
    avg_kda: Optional[float] = None
    avg_kp: Optional[float] = None
    avg_gpm: Optional[float] = None
    avg_cspm: Optional[float] = None
    source: str = "api"
