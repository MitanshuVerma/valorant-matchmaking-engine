from fastapi import APIRouter, HTTPException
from app.schemas.telemetry import PlayerTelemetryResponse
from app.services.riot_api import riot_client
from app.db.redis import get_cache, set_cache

router = APIRouter()

@router.get("/stats/{game_name}/{tag_line}", response_model=PlayerTelemetryResponse)
async def get_player_stats(game_name: str, tag_line: str):
    cache_key = f"telemetry:{game_name}:{tag_line}"
    
    try:
        # 1. Check Cache
        cached_data = await get_cache(cache_key)
        if cached_data:
            cached_data["source"] = "cache"
            return PlayerTelemetryResponse(**cached_data)
            
        # 2. Fetch and Parse from Riot API
        # We don't have the PUUID upfront, so parse_player_telemetry handles it
        parsed_data = await riot_client.parse_player_telemetry(None, game_name, tag_line)
        
        # 3. Set Cache (5-minute TTL)
        await set_cache(cache_key, parsed_data, ttl=300)
        
        return PlayerTelemetryResponse(**parsed_data)
        
    except Exception as e:
        # In a real app, you'd check for specific HTTPX errors to return 404 or 429
        raise HTTPException(status_code=500, detail=f"Failed to fetch telemetry: {str(e)}")
