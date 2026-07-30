import random
import time
import logging

logger = logging.getLogger(__name__)

# Complete list of all 26 VALORANT Agents & their roles
ALL_VALORANT_AGENTS = [
    # Duelists
    ("Jett", "Duelist"), ("Reyna", "Duelist"), ("Raze", "Duelist"),
    ("Phoenix", "Duelist"), ("Yoru", "Duelist"), ("Neon", "Duelist"), ("Iso", "Duelist"),
    # Initiators
    ("Sova", "Initiator"), ("Breach", "Initiator"), ("Skye", "Initiator"),
    ("KAY/O", "Initiator"), ("Fade", "Initiator"), ("Gekko", "Initiator"), ("Tejo", "Initiator"),
    # Controllers
    ("Omen", "Controller"), ("Brimstone", "Controller"), ("Viper", "Controller"),
    ("Astra", "Controller"), ("Harbor", "Controller"), ("Clove", "Controller"),
    # Sentinels
    ("Sage", "Sentinel"), ("Cypher", "Sentinel"), ("Killjoy", "Sentinel"),
    ("Chamber", "Sentinel"), ("Deadlock", "Sentinel"), ("Vyse", "Sentinel")
]

VALORANT_PRO_NAMES = [
    ("TenZ", "SEN"), ("aspas", "LEV"), ("Derke", "FNC"), ("Boaster", "FNC"),
    ("Chronicle", "FNC"), ("Demon1", "NRG"), ("Yay", "BLEED"), ("cned", "FUT"),
    ("ScreaM", "EDG"), ("buzz", "T1"), ("stax", "DRX"), ("rb", "TE"),
    ("MaKo", "DRX"), ("Marved", "SEN"), ("Zellsis", "SEN"), ("Sacy", "SEN"),
    ("Suygetsu", "NAV"), ("Alfajer", "FNC"), ("Leo", "FNC"), ("Cryocells", "100T"),
    ("Asuna", "100T"), ("Bang", "SEN"), ("zekken", "SEN"), ("valyn", "G2"),
    ("trent", "G2"), ("leaf", "G2")
]

class AIValorantPlayerGenerator:
    """Generates realistic AI VALORANT players with unconstrained MMR (0 to 10,000+)."""

    @staticmethod
    def generate_players(count: int = 9, base_mmr: float = 2000.0) -> list[dict]:
        sampled_names = random.sample(VALORANT_PRO_NAMES, min(count, len(VALORANT_PRO_NAMES)))
        sampled_agents = random.sample(ALL_VALORANT_AGENTS, min(count, len(ALL_VALORANT_AGENTS)))
        
        ai_players = []
        for i in range(count):
            if i < len(sampled_names):
                name, tag = sampled_names[i]
            else:
                name, tag = f"Agent_{random.randint(100, 999)}", f"VAL{random.randint(10, 99)}"

            if i < len(sampled_agents):
                agent, role = sampled_agents[i]
            else:
                agent, role = random.choice(ALL_VALORANT_AGENTS)

            # Unconstrained MMR: Variance capped to 70 to ensure max difference <= 140 (fits within 150 max_mmr_gap)
            mmr_variance = min(70.0, max(30.0, base_mmr * 0.05))
            mmr = max(0.0, round(base_mmr + random.uniform(-mmr_variance, mmr_variance), 1))

            # Dynamically infer rank string from MMR value
            if mmr >= 2500:
                rank = "Radiant"
            elif mmr >= 2100:
                rank = f"Immortal {random.randint(1, 3)}"
            elif mmr >= 1700:
                rank = f"Ascendant {random.randint(1, 3)}"
            elif mmr >= 1300:
                rank = f"Diamond {random.randint(1, 3)}"
            elif mmr >= 900:
                rank = f"Gold {random.randint(1, 3)}"
            elif mmr >= 400:
                rank = f"Bronze {random.randint(1, 3)}"
            else:
                rank = "Iron 1"

            kda = round(random.uniform(1.15, 2.45), 2)
            acs = random.randint(180, 320)
            hs_pct = f"{random.randint(22, 48)}%"
            ping = random.randint(12, 42)

            player_id = f"{name}#{tag}"
            ai_players.append({
                "player_id": player_id,
                "game_name": name,
                "tag_line": tag,
                "agent": agent,
                "role": role,
                "rank": rank,
                "mmr": mmr,
                "kda": kda,
                "acs": acs,
                "headshot_pct": hs_pct,
                "max_ping": ping,
                "queue_join_timestamp": time.time(),
                "is_ai": True
            })
            
        return ai_players

ai_generator = AIValorantPlayerGenerator()
