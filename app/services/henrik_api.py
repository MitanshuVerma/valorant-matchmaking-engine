import httpx
import logging
from app.config import settings
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class HenrikAPIClient:
    def __init__(self):
        self.base_url = "https://api.henrikdev.xyz/valorant"
        self.api_key = getattr(settings, "henrik_api_key", "")
        self.headers = {
            "Authorization": self.api_key
        }

    async def get_player_stats(self, game_name: str, tag_line: str) -> dict:
        if not self.api_key:
            return None
            
        try:
            async with httpx.AsyncClient() as client:
                # 1. Fetch Account (Region)
                account_url = f"{self.base_url}/v1/account/{game_name}/{tag_line}"
                acc_res = await client.get(account_url, headers=self.headers, timeout=10.0)
                if acc_res.status_code == 404:
                    logger.warning(f"Account {game_name}#{tag_line} not found (404).")
                    return None
                if acc_res.status_code in [401, 403]:
                    raise HTTPException(status_code=500, detail="Henrik API Key is invalid or unauthorized!")
                acc_res.raise_for_status()
                acc_data = acc_res.json()
                region = acc_data.get("data", {}).get("region", "na")

                # 2. Fetch MMR/Rank using Region
                mmr_url = f"{self.base_url}/v1/mmr/{region}/{game_name}/{tag_line}"
                mmr_res = await client.get(mmr_url, headers=self.headers, timeout=10.0)
                
                if mmr_res.status_code == 404:
                    logger.warning(f"Player {game_name}#{tag_line} has no MMR data (404). Falling back.")
                    return None
                    
                mmr_res.raise_for_status()
                mmr_data = mmr_res.json()
                rank_str = mmr_data.get("data", {}).get("currenttierpatched", "Unranked")

                # 3. Fetch Match History for KDA and ACS using Region
                matches_url = f"{self.base_url}/v1/lifetime/matches/{region}/{game_name}/{tag_line}?mode=competitive&size=5"
                matches_res = await client.get(matches_url, headers=self.headers, timeout=10.0)
                matches_res.raise_for_status()
                matches_data = matches_res.json()
                
                matches = matches_data.get("data", [])
                if not matches:
                    return {
                        "kda": 1.0,
                        "acs": 200,
                        "rank": rank_str,
                        "latest_match_id": None
                    }
                    
                total_kills = 0
                total_deaths = 0
                total_assists = 0
                total_score = 0
                total_rounds = 0
                
                for m in matches:
                    stats = m.get("stats", {})
                    total_kills += stats.get("kills", 0)
                    total_deaths += stats.get("deaths", 0)
                    total_assists += stats.get("assists", 0)
                    total_score += stats.get("score", 0)
                    
                    teams = m.get("teams", {})
                    red = teams.get("red", 0)
                    blue = teams.get("blue", 0)
                    total_rounds += (red + blue)
                
                kd = total_kills / max(1, total_deaths)
                acs = (total_score / max(1, total_rounds)) if total_rounds > 0 else 200
                
                # Get the most recent Match ID to fetch other players
                latest_match_id = matches[0].get("meta", {}).get("id") if matches else None
                
                return {
                    "kda": round(kd, 2),
                    "acs": round(acs, 1),
                    "rank": rank_str,
                    "latest_match_id": latest_match_id
                }
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code in [401, 403]:
                raise HTTPException(status_code=500, detail="Henrik API Key is invalid or unauthorized!")
            if e.response.status_code == 404:
                logger.warning(f"Player {game_name}#{tag_line} not found (404). Falling back.")
                return None
            logger.error(f"Henrik API Error for {game_name}#{tag_line}: {e}")
            return None
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            logger.error(f"Unexpected Henrik API Error: {e}")
            return None

    async def get_match_players(self, match_id: str, exclude_game_name: str, exclude_tag_line: str) -> list:
        if not self.api_key or not match_id:
            return []
            
        try:
            async with httpx.AsyncClient() as client:
                match_url = f"{self.base_url}/v2/match/{match_id}"
                res = await client.get(match_url, headers=self.headers, timeout=10.0)
                if res.status_code == 404:
                    return []
                res.raise_for_status()
                data = res.json().get("data", {})
                
                rounds_played = data.get("metadata", {}).get("rounds_played", 20)
                all_players = data.get("players", {}).get("all_players", [])
                
                real_players = []
                for p in all_players:
                    p_name = p.get("name", "")
                    p_tag = p.get("tag", "")
                    
                    # Skip the querying user
                    if p_name.lower() == exclude_game_name.lower() and p_tag.lower() == exclude_tag_line.lower():
                        continue
                        
                    stats = p.get("stats", {})
                    kills = stats.get("kills", 0)
                    deaths = stats.get("deaths", 0)
                    assists = stats.get("assists", 0)
                    score = stats.get("score", 0)
                    
                    kd = kills / max(1, deaths)
                    acs = (score / max(1, rounds_played))
                    
                    real_players.append({
                        "game_name": p_name,
                        "tag_line": p_tag,
                        "agent": p.get("character", "Jett"),
                        "rank": p.get("currenttier_patched", "Unranked"),
                        "kda": round(kd, 2),
                        "acs": round(acs, 1)
                    })
                    
                return real_players
        except Exception as e:
            logger.error(f"Failed to fetch match players: {e}")
            return []

henrik_client = HenrikAPIClient()
