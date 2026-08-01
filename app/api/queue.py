from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from app.schemas.queue import QueueJoinRequest, QueueResponse, QueueLeaveRequest
from app.db.redis import zadd_player, zrem_player, get_queue_range
from app.core.queue import QUEUE_NAME
from app.services.ai_generator import ai_generator
from app.services.riot_api import riot_client
from app.services.tracker_api import tracker_client
from app.db.postgres import AsyncSessionLocal
from app.db.models import PlayerStat
from sqlalchemy.future import select
from sqlalchemy import func
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
    """Background task: Pulls 9 closest players from Postgres pool, fetches TRN stats, adds to Redis."""
    logger.info(f"Queued player {user_payload['player_id']}. Querying Postgres for 9 closest players...")
    
    selected_players = []
    
    # 1. Query Postgres for the 9 closest MMR players
    async with AsyncSessionLocal() as db:
        # Avoid pulling the user themselves
        stmt = (
            select(PlayerStat)
            .where(PlayerStat.player_id != user_payload["player_id"])
            .order_by(func.abs(PlayerStat.current_mmr - user_mmr))
            .limit(9)
        )
        result = await db.execute(stmt)
        db_players = result.scalars().all()
        
    if len(db_players) < 9:
        logger.warning(f"Only found {len(db_players)} players in DB. Filling rest with AI generator.")
        
    for p in db_players:
        parts = p.player_id.split("#")
        game_name = parts[0]
        tag_line = parts[1] if len(parts) > 1 else "NA1"
        
        # 2. Fetch TRN stats
        logger.info(f"Fetching TRN stats for {p.player_id}...")
        trn_stats = await tracker_client.get_player_stats(game_name, tag_line)
        
        if trn_stats:
            kda = trn_stats["kda"]
            acs = trn_stats["acs"]
            rank = trn_stats["rank"]
            stats_source = "Tracker.gg (Live)"
        else:
            # Fallback if profile is private or TRN 404s
            kda = round(random.uniform(0.8, 1.4) + (p.current_mmr / 5000), 2)
            acs = random.randint(150, 240) + int(p.current_mmr / 100)
            rank = "Immortal 1" if p.current_mmr > 2000 else ("Iron 1" if p.current_mmr < 500 else "Gold 2")
            stats_source = "TRN Fallback"
            
        player_payload = {
            "player_id": p.player_id,
            "game_name": game_name,
            "tag_line": tag_line,
            "agent": random.choice(["Jett", "Reyna", "Omen", "Sova", "Killjoy", "Cypher"]),
            "role": random.choice(["Duelist", "Initiator", "Controller", "Sentinel"]),
            "rank": rank,
            "mmr": p.current_mmr,
            "kda": kda,
            "acs": acs,
            "headshot_pct": f"{random.randint(15, 45)}%",
            "max_ping": random.randint(15, 65),
            "queue_join_timestamp": time.time(),
            "stats_source": stats_source,
            "is_ai": False
        }
        
        selected_players.append(player_payload)
        # Sleep for 1.2s to respect TRN rate limits
        await asyncio.sleep(1.2)
        
    # If we didn't find 9 in DB, fill with AI
    if len(selected_players) < 9:
        ai_players = ai_generator.generate_players(count=9 - len(selected_players), base_mmr=user_mmr)
        selected_players.extend(ai_players)
        
    # Add all to Redis
    for sp in selected_players:
        await zadd_player(QUEUE_NAME, sp["mmr"], sp)
        
    logger.info(f"Added 9 players to Redis ZSET. Background worker will now form 5v5 match.")

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
    """Fetches TRN telemetry for user, saves them to Postgres pool, then triggers delayed 9 player population."""
    try:
        if "#" in request.game_name:
            parts = request.game_name.split("#", 1)
            request.game_name = parts[0]
            request.tag_line = parts[1]
            
        user_player_id = f"{request.game_name}#{request.tag_line}"

        # 1. Identity Validation (Riot API)
        if settings.riot_api_key and settings.riot_api_key.startswith("RGAPI"):
            try:
                logger.info(f"Validating {user_player_id} via Riot API...")
                await riot_client.parse_player_telemetry(None, request.game_name, request.tag_line)
            except Exception as riot_err:
                if "404" in str(riot_err):
                    logger.error(f"Riot API returned 404: {user_player_id} does not exist.")
                    raise HTTPException(status_code=404, detail=f"Invalid Riot ID! {user_player_id} does not exist on Riot Servers.")
                logger.warning(f"Could not validate via Riot API ({riot_err}).")

        # 2. Fetch User Stats (Tracker API)
        real_kda = round(random.uniform(1.0, 1.8) + (request.user_mmr / 5000), 2)
        real_acs = random.randint(190, 270) + int(request.user_mmr / 100)
        rank_str = "Immortal 1" if request.user_mmr > 2000 else ("Iron 1" if request.user_mmr < 500 else "Gold 2")
        stats_source = "simulated"

        if settings.trn_api_key:
            logger.info(f"Fetching live TRN stats for {user_player_id}...")
            trn_stats = await tracker_client.get_player_stats(request.game_name, request.tag_line)
            if trn_stats:
                real_kda = trn_stats["kda"]
                real_acs = trn_stats["acs"]
                rank_str = trn_stats["rank"]
                stats_source = "Tracker.gg (Live)"

        # 3. Add to Postgres Player Pool (Self-Growing DB)
        async with AsyncSessionLocal() as db:
            existing = await db.execute(select(PlayerStat).where(PlayerStat.player_id == user_player_id))
            stat = existing.scalar_one_or_none()
            if stat:
                stat.current_mmr = request.user_mmr
            else:
                stat = PlayerStat(
                    player_id=user_player_id,
                    puuid=None,
                    current_mmr=request.user_mmr,
                    match_count=0
                )
                db.add(stat)
            await db.commit()

        user_payload = {
            "player_id": user_player_id,
            "game_name": request.game_name,
            "tag_line": request.tag_line,
            "agent": request.agent,
            "role": request.role,
            "rank": rank_str,
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

        # Schedule background delayed population (queries DB for 9 real players)
        background_tasks.add_task(delayed_ai_population, user_payload, request.user_mmr)

        return {
            "status": "success",
            "message": f"Enqueued user ({stats_source}). Searching for players...",
            "user_id": user_player_id,
            "user_payload": user_payload
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
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
