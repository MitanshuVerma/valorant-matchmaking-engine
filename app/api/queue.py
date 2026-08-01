from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from app.schemas.queue import QueueJoinRequest, QueueResponse, QueueLeaveRequest
from app.db.redis import zadd_player, zrem_player, get_queue_range
from app.core.queue import QUEUE_NAME
from app.services.ai_generator import ai_generator
from app.services.riot_api import riot_client
from app.services.henrik_api import henrik_client
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

def get_rank_for_mmr(mmr: float) -> str:
    ranks = [
        "Iron 1", "Iron 2", "Iron 3",
        "Bronze 1", "Bronze 2", "Bronze 3",
        "Silver 1", "Silver 2", "Silver 3",
        "Gold 1", "Gold 2", "Gold 3",
        "Platinum 1", "Platinum 2", "Platinum 3",
        "Diamond 1", "Diamond 2", "Diamond 3",
        "Ascendant 1", "Ascendant 2", "Ascendant 3",
        "Immortal 1", "Immortal 2", "Immortal 3",
        "Radiant"
    ]
    # Base index calculation based on max MMR 3000
    base_index = int((mmr / 3000.0) * len(ranks))
    # Add random variance of -2 to +2 ranks
    variance = random.randint(-2, 2)
    final_index = max(0, min(len(ranks) - 1, base_index + variance))
    return ranks[final_index]

async def delayed_match_population(user_payload: dict, user_mmr: float, latest_match_id: str):
    """Background task: Pulls 9 players from the user's latest real match, falls back to Postgres if needed."""
    logger.info(f"Queued player {user_payload['player_id']}. Fetching real players from match {latest_match_id}...")
    
    selected_players = []
    
    # 1. Try to fetch 9 real players from the recent match
    if latest_match_id:
        real_players = await henrik_client.get_match_players(
            latest_match_id, 
            user_payload["game_name"], 
            user_payload["tag_line"]
        )
        for rp in real_players:
            player_payload = {
                "player_id": f"{rp['game_name']}#{rp['tag_line']}",
                "game_name": rp['game_name'],
                "tag_line": rp['tag_line'],
                "agent": rp['agent'],
                "role": random.choice(["Duelist", "Initiator", "Controller", "Sentinel"]), # Simplified role
                "rank": rp['rank'],
                "mmr": user_mmr, # Keep MMR same as user to ensure match pops instantly
                "kda": rp['kda'],
                "acs": rp['acs'],
                "headshot_pct": f"{random.randint(15, 45)}%",
                "max_ping": random.randint(15, 65),
                "queue_join_timestamp": time.time(),
                "stats_source": "HenrikDev (Match History)",
                "is_ai": False
            }
            selected_players.append(player_payload)
            
    # 2. If we didn't get enough (e.g. no match ID), fall back to DB
    if len(selected_players) < 9:
        logger.warning(f"Only found {len(selected_players)} players in match. Filling rest from DB.")
        async with AsyncSessionLocal() as db:
            stmt = (
                select(PlayerStat)
                .where(PlayerStat.player_id != user_payload["player_id"])
                .order_by(func.abs(PlayerStat.current_mmr - user_mmr))
                .limit(9 - len(selected_players))
            )
            result = await db.execute(stmt)
            db_players = result.scalars().all()
            
        for p in db_players:
            parts = p.player_id.split("#")
            game_name = parts[0]
            tag_line = parts[1] if len(parts) > 1 else "NA1"
            player_payload = {
                "player_id": p.player_id,
                "game_name": game_name,
                "tag_line": tag_line,
                "agent": random.choice(["Jett", "Reyna", "Omen", "Sova", "Killjoy", "Cypher"]),
                "role": random.choice(["Duelist", "Initiator", "Controller", "Sentinel"]),
                "rank": get_rank_for_mmr(p.current_mmr),
                "mmr": p.current_mmr,
                "kda": round(random.uniform(0.8, 1.4) + (p.current_mmr / 5000), 2),
                "acs": random.randint(150, 240) + int(p.current_mmr / 100),
                "headshot_pct": f"{random.randint(15, 45)}%",
                "max_ping": random.randint(15, 65),
                "queue_join_timestamp": time.time(),
                "stats_source": "Fallback DB",
                "is_ai": False
            }
            selected_players.append(player_payload)
            
    # If still not 9, fill with AI just to avoid breaking the matchmaker completely
    if len(selected_players) < 9:
        ai_players = ai_generator.generate_players(count=9 - len(selected_players), base_mmr=user_mmr)
        selected_players.extend(ai_players)
        
    # Add all to Redis
    for sp in selected_players:
        await zadd_player(QUEUE_NAME, sp["mmr"], sp)
        
    logger.info(f"Added {len(selected_players)} players to Redis ZSET. Background worker will now form 5v5 match.")

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

        # 2. Fetch User Stats (Henrik API)
        real_kda = round(random.uniform(1.0, 1.8) + (request.user_mmr / 5000), 2)
        real_acs = random.randint(190, 270) + int(request.user_mmr / 100)
        rank_str = get_rank_for_mmr(request.user_mmr)
        stats_source = "simulated"
        latest_match_id = None

        if settings.henrik_api_key:
            logger.info(f"Fetching live stats from HenrikDev API for {user_player_id}...")
            henrik_stats = await henrik_client.get_player_stats(request.game_name, request.tag_line)
            if henrik_stats:
                real_kda = henrik_stats["kda"]
                real_acs = henrik_stats["acs"]
                rank_str = henrik_stats["rank"]
                latest_match_id = henrik_stats.get("latest_match_id")
                stats_source = "HenrikDev (Live)"

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
            "is_ai": False,
            "is_real_user": True
        }
        
        # Enqueue user immediately
        await zadd_player(QUEUE_NAME, request.user_mmr, user_payload)

        # Schedule background delayed population (queries Henrik for 9 match players)
        background_tasks.add_task(delayed_match_population, user_payload, request.user_mmr, latest_match_id)

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
