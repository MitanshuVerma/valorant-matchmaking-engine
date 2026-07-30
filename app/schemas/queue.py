from pydantic import BaseModel
from typing import Optional

class QueueJoinRequest(BaseModel):
    player_id: str
    mmr: float
    role: str
    max_ping: int

class QueueResponse(BaseModel):
    status: str
    message: str
    player_id: str
    
class QueueLeaveRequest(BaseModel):
    player_id: str
