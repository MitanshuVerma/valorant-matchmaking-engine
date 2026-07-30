import httpx
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class RiotAPIClient:
    def __init__(self):
        self.headers = {
            "X-Riot-Token": settings.riot_api_key
        }
        self.base_url_americas = "https://americas.api.riotgames.com" # Using Americas routing for Account & Match V5 as per Riot guidelines

    async def get_puuid(self, game_name: str, tag_line: str) -> str:
        url = f"{self.base_url_americas}/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            return data.get("puuid")

    async def get_latest_match_ids(self, puuid: str, count: int = 5) -> list[str]:
        url = f"{self.base_url_americas}/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count={count}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def get_match_details(self, match_id: str) -> dict:
        url = f"{self.base_url_americas}/lol/match/v5/matches/{match_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def parse_player_telemetry(self, puuid: str, game_name: str, tag_line: str) -> dict:
        try:
            actual_puuid = puuid or await self.get_puuid(game_name, tag_line)
            match_ids = await self.get_latest_match_ids(actual_puuid)
            
            if not match_ids:
                return {
                    "puuid": actual_puuid,
                    "game_name": game_name,
                    "tag_line": tag_line,
                    "match_count": 0,
                    "avg_kda": None,
                    "avg_kp": None,
                    "avg_gpm": None,
                    "avg_cspm": None
                }

            total_kda = 0.0
            total_kp = 0.0
            total_gpm = 0.0
            total_cspm = 0.0
            valid_matches = 0

            for match_id in match_ids:
                match_data = await self.get_match_details(match_id)
                info = match_data.get("info", {})
                participants = info.get("participants", [])
                
                # Find our player and team kills
                player_data = None
                team_id = None
                for p in participants:
                    if p.get("puuid") == actual_puuid:
                        player_data = p
                        team_id = p.get("teamId")
                        break
                        
                if not player_data:
                    continue

                team_kills = 0
                for p in participants:
                    if p.get("teamId") == team_id:
                        team_kills += p.get("kills", 0)

                kills = player_data.get("kills", 0)
                deaths = player_data.get("deaths", 0)
                assists = player_data.get("assists", 0)
                
                # KDA
                kda = (kills + assists) / max(1, deaths)
                total_kda += kda
                
                # KP
                kp = ((kills + assists) / max(1, team_kills)) * 100 if team_kills > 0 else 0
                total_kp += kp
                
                game_duration_min = info.get("gameDuration", 1) / 60.0
                
                # GPM
                gold_earned = player_data.get("goldEarned", 0)
                gpm = gold_earned / max(1, game_duration_min)
                total_gpm += gpm
                
                # CSPM
                cs = player_data.get("totalMinionsKilled", 0) + player_data.get("neutralMinionsKilled", 0)
                cspm = cs / max(1, game_duration_min)
                total_cspm += cspm
                
                valid_matches += 1

            if valid_matches == 0:
                return {
                    "puuid": actual_puuid,
                    "game_name": game_name,
                    "tag_line": tag_line,
                    "match_count": 0,
                    "avg_kda": None,
                    "avg_kp": None,
                    "avg_gpm": None,
                    "avg_cspm": None
                }
                 
            return {
                "puuid": actual_puuid,
                "game_name": game_name,
                "tag_line": tag_line,
                "match_count": valid_matches,
                "avg_kda": round(total_kda / valid_matches, 2),
                "avg_kp": round(total_kp / valid_matches, 2),
                "avg_gpm": round(total_gpm / valid_matches, 2),
                "avg_cspm": round(total_cspm / valid_matches, 2)
            }
            
        except Exception as e:
            logger.error(f"Error fetching telemetry for {game_name}#{tag_line}: {e}")
            raise

riot_client = RiotAPIClient()
