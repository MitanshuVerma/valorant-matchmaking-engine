from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from app.schemas.queue import QueueJoinRequest, QueueResponse, QueueLeaveRequest
from app.db.redis import zadd_player, zrem_player, get_queue_range
from app.core.queue import QUEUE_NAME
from app.services.ai_generator import ai_generator
from app.services.riot_api import riot_client
from app.config import settings
import asyncio
import random
import time
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class AutoMatchRequest(BaseModel):
    game_name: str
    tag_line: str
    role: str = "Duelist"
    agent: str = "Jett"
    user_mmr: float = 2150.0

async def delayed_ai_population(user_payload: dict, user_mmr: float):
    """Background task: waits 7-15 seconds before populating the remaining 9 AI players into Redis ZSET."""
    delay = random.uniform(7.0, 15.0)
    logger.info(f"Queued player {user_payload['player_id']}. Simulating matchmaking queue search delay of {delay:.1f}s...")
    await asyncio.sleep(delay)

    # Generate 9 AI players matching the user's MMR scale
    ai_players = ai_generator.generate_players(count=9, base_mmr=user_mmr)
    for ai in ai_players:
        await zadd_player(QUEUE_NAME, ai["mmr"], ai)
    
    logger.info(f"Added 9 AI players to Redis ZSET. Background worker will now form 5v5 match.")

@router.post("/join", response_model=QueueResponse, status_code=status.HTTP_201_CREATED)
async def join_queue(request: QueueJoinRequest):
    try:
        payload = {
            "player_id": request.player_id,
            "game_name": request.player_id.split("#")[0],
            "tag_line": request.player_id.split("#")[1] if "#" in request.player_id else "VAL",
            "role": request.role,
            "agent": "Jett",
            "rank": "Ascendant 2",
            "max_ping": request.max_ping,
            "mmr": request.mmr,
            "kda": 1.45,
            "acs": 230,
            "headshot_pct": "31%",
            "queue_join_timestamp": time.time(),
            "is_ai": False
        }
        await zadd_player(QUEUE_NAME, request.mmr, payload)
        return QueueResponse(status="success", message="Joined queue", player_id=request.player_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auto-match")
async def auto_match_simulation(request: AutoMatchRequest, background_tasks: BackgroundTasks):
    """Fetches REAL telemetry from Riot API if key is set, then populates 9 AI players after 7-15s delay."""
    try:
        if "#" in request.game_name:
            parts = request.game_name.split("#", 1)
            request.game_name = parts[0]
            request.tag_line = parts[1]
            
        user_player_id = f"{request.game_name}#{request.tag_line}"

        # Generate realistic fallback stats based on selected MMR
        real_kda = round(random.uniform(1.0, 1.8) + (request.user_mmr / 5000), 2)
        real_acs = random.randint(190, 270) + int(request.user_mmr / 100)
        stats_source = "simulated"

        # Attempt to fetch REAL telemetry from Riot Games API if key is present
        if settings.riot_api_key and settings.riot_api_key.startswith("RGAPI"):
            try:
                logger.info(f"Fetching real telemetry from Riot API for {user_player_id}...")
                telemetry = await riot_client.parse_player_telemetry(None, request.game_name, request.tag_line)
                if telemetry.get("avg_kda") is not None:
                    real_kda = telemetry["avg_kda"]
                    stats_source = "Riot API (Live)"
                    logger.info(f"Successfully fetched live Riot API KDA: {real_kda}")
            except Exception as riot_err:
                if "404" in str(riot_err):
                    logger.error(f"Riot API returned 404: {user_player_id} does not exist.")
                    raise HTTPException(status_code=404, detail=f"Invalid Riot ID! {user_player_id} does not exist on Riot Servers.")
                logger.warning(f"Could not fetch from Riot API ({riot_err}). Falling back to simulation.")

        user_payload = {
            "player_id": user_player_id,
            "game_name": request.game_name,
            "tag_line": request.tag_line,
            "agent": request.agent,
            "role": request.role,
            "rank": "Immortal 1" if request.user_mmr > 2000 else ("Iron 1" if request.user_mmr < 500 else "Gold 2"),
            "mmr": request.user_mmr,
            "kda": real_kda,
            "acs": real_acs,
            "headshot_pct": "38%",
            "max_ping": 18,
            "queue_join_timestamp": time.time(),
            "stats_source": stats_source,
            "is_ai": False
        }
        
        # Enqueue user immediately
        await zadd_player(QUEUE_NAME, request.user_mmr, user_payload)

        # Schedule background delayed population (7-15s)
        background_tasks.add_task(delayed_ai_population, user_payload, request.user_mmr)

        return {
            "status": "success",
            "message": f"Enqueued user ({stats_source}). Searching for players...",
            "user_id": user_player_id,
            "user_payload": user_payload
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list")
async def get_current_queue():
    queued_tuples = await get_queue_range(QUEUE_NAME, withscores=True)
    players = []
    for payload_str, mmr in queued_tuples:
        data = json.loads(payload_str)
        players.append(data)
    return {"count": len(players), "players": players}

@router.post("/leave", response_model=QueueResponse)
async def leave_queue(request: QueueLeaveRequest):
    try:
        queued_players = await get_queue_range(QUEUE_NAME, withscores=False)
        target_payload_str = None
        
        for payload_str in queued_players:
            data = json.loads(payload_str)
            if data.get("player_id") == request.player_id:
                target_payload_str = payload_str
                break
                
        if target_payload_str:
            await zrem_player(QUEUE_NAME, target_payload_str)
            return QueueResponse(status="success", message="Left queue", player_id=request.player_id)
        else:
            raise HTTPException(status_code=404, detail="Player not found in queue")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
