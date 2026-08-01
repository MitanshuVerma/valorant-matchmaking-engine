import httpx
import logging
from app.config import settings

logger = logging.getLogger(__name__)

class TrackerAPIClient:
    def __init__(self):
        self.base_url = "https://public-api.tracker.gg/v2/valorant/standard/profile/riot"
        self.api_key = getattr(settings, "trn_api_key", "")
        self.headers = {
            "TRN-Api-Key": self.api_key
        }

    async def get_player_stats(self, game_name: str, tag_line: str) -> dict:
        if not self.api_key:
            return None
            
        url = f"{self.base_url}/{game_name}%23{tag_line}"
        try:
            async with httpx.AsyncClient() as client:
                # Add a 10-second timeout
                response = await client.get(url, headers=self.headers, timeout=10.0)
                if response.status_code == 404:
                    from fastapi import HTTPException
                    raise HTTPException(status_code=404, detail=f"Player {game_name}#{tag_line} does not exist on Tracker.gg!")
                response.raise_for_status()
                data = response.json()
                
                # Parse the TRN data structure for competitive overview
                segments = data.get("data", {}).get("segments", [])
                if not segments:
                    return None
                    
                # Look for the overview segment
                overview = next((s for s in segments if s.get("type") == "overview"), None)
                if not overview:
                    return None
                    
                stats = overview.get("stats", {})
                
                # Extract specific stats
                kda = stats.get("kdaRatio", {}).get("value", 0.0)
                # TRN calls ACS 'scorePerRound' usually, or sometimes 'damagePerRound'
                acs = stats.get("scorePerRound", {}).get("value", 0.0)
                rank_str = stats.get("rank", {}).get("metadata", {}).get("tierName", "Unranked")
                
                return {
                    "kda": round(kda, 2),
                    "acs": round(acs, 1),
                    "rank": rank_str
                }
        except httpx.HTTPError as e:
            logger.error(f"TRN API Error for {game_name}#{tag_line}: {e}")
            return None
        except Exception as e:
            from fastapi import HTTPException
            if isinstance(e, HTTPException):
                raise
            logger.error(f"Unexpected TRN API Error: {e}")
            return None

tracker_client = TrackerAPIClient()
