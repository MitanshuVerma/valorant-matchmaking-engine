import asyncio
import json
import uuid
import time
import logging
from app.db.redis import get_queue_range, zrem_player
from app.db.postgres import AsyncSessionLocal
from app.db.models import Match
from app.config import settings
from app.api.ws import ws_manager

logger = logging.getLogger(__name__)

QUEUE_NAME = "matchmaking_queue"
VALORANT_MAPS = ["Haven", "Bind", "Ascent", "Split", "Icebox", "Lotus", "Sunset"]

async def persist_match(players: list[dict]):
    """Persists a formed match to PostgreSQL / SQLite and notifies players via WebSocket."""
    lobby_id = str(uuid.uuid4())
    avg_mmr = sum(p["mmr"] for p in players) / len(players)
    map_selected = VALORANT_MAPS[hash(lobby_id) % len(VALORANT_MAPS)]

    # Split 10 players into Attackers (5) vs Defenders (5)
    sorted_players = sorted(players, key=lambda x: x["mmr"], reverse=True)
    attackers = sorted_players[::2]  # Alternate picking for balanced teams
    defenders = sorted_players[1::2]

    match_payload = {
        "lobby_id": lobby_id,
        "status": "formed",
        "map": map_selected,
        "average_mmr": round(avg_mmr, 1),
        "attackers": attackers,
        "defenders": defenders,
        "total_players": len(players)
    }

    async with AsyncSessionLocal() as session:
        new_match = Match(
            lobby_id=lobby_id,
            status="formed",
            players=match_payload,
            average_mmr=avg_mmr
        )
        session.add(new_match)
        await session.commit()

    logger.info(f"VALORANT 5v5 Match formed: {lobby_id} on {map_selected} (Avg MMR {avg_mmr:.1f})")

    # Broadcast MATCH_FOUND event to all connected WebSocket clients
    for player in players:
        p_id = player.get("player_id")
        if p_id:
            await ws_manager.broadcast_to_player(p_id, {
                "type": "MATCH_FOUND",
                "data": match_payload
            })

async def matchmaking_worker():
    """Background task that continuously scans the Redis ZSET to form 5v5 matches."""
    logger.info("Matchmaking worker started.")
    
    while True:
        try:
            # Fetch players ordered by MMR
            queued_players = await get_queue_range(QUEUE_NAME, withscores=True)
            
            if len(queued_players) < settings.lobby_size:
                await asyncio.sleep(1.5)
                continue

            # queued_players is a list of tuples: [(payload_str, mmr), ...]
            
            # Simple sliding window approach to find a valid lobby
            i = 0
            while i <= len(queued_players) - settings.lobby_size:
                lobby_candidates = []
                current_time = time.time()
                
                # Check consecutive players to form a 10-player lobby
                valid_lobby = True
                
                for j in range(settings.lobby_size):
                    payload_str, mmr = queued_players[i + j]
                    player_data = json.loads(payload_str)
                    
                    # Calculate dynamic MMR tolerance
                    time_in_queue = current_time - player_data.get("queue_join_timestamp", current_time)
                    expansion_multiplier = int(time_in_queue // settings.mmr_expansion_interval_sec)
                    current_tolerance = settings.max_mmr_gap + (expansion_multiplier * settings.mmr_expansion_rate)
                    
                    lobby_candidates.append({
                        "payload_str": payload_str,
                        "data": player_data,
                        "mmr": mmr,
                        "tolerance": current_tolerance
                    })

                # Validate the lobby (Check max difference against tolerances)
                min_mmr = min(c["mmr"] for c in lobby_candidates)
                max_mmr = max(c["mmr"] for c in lobby_candidates)
                mmr_diff = max_mmr - min_mmr
                
                for c in lobby_candidates:
                    if mmr_diff > c["tolerance"]:
                        valid_lobby = False
                        break

                if valid_lobby:
                    # Remove from queue
                    for c in lobby_candidates:
                        await zrem_player(QUEUE_NAME, c["payload_str"])
                    
                    # Persist match & broadcast via WS
                    players_to_persist = [c["data"] for c in lobby_candidates]
                    await persist_match(players_to_persist)
                    
                    # Restart scan after forming a match
                    break 
                else:
                    i += 1
            
            await asyncio.sleep(1)
            
        except asyncio.CancelledError:
            logger.info("Matchmaking worker shutting down.")
            break
        except Exception as e:
            logger.error(f"Error in matchmaking worker: {e}")
            await asyncio.sleep(3)
