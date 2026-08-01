import logging
import random
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.models import PlayerStat

logger = logging.getLogger(__name__)

# Mix of Pros, Streamers, and extremely common tags that are guaranteed to exist
# Ranks will be simulated by assigning random MMRs, but their real rank will be fetched from TRN!
SEED_PLAYERS = [
    "TenZ#SEN", "tarik#tarik", "zekken#SEN", "s0m#W", "FNS#G", "Subroza#G", "Kyedae#Ribey", 
    "yay#C9", "Boaster#FNC", "Derke#FNC", "nAts#TL", "Jamppi#TL", "Chronicle#FNC",
    "Leo#FNC", "Alfajer#FNC", "Demon1#NRG", "Ethan#NRG", "crashies#NRG", "Victor#NRG",
    "Marved#NRG", "Somis#W", "ShahZaM#G2", "dapr#SEN", "SicK#SEN", "zombs#SEN",
    "Asuna#100T", "bang#100T", "Cryocells#100T", "stellar#100T", "Derrek#100T",
    "Tenzin#NA1", "John#NA1", "Alex#NA1", "Ghost#NA1", "Shadow#NA1", "Ninja#NA1",
    "Viper#NA1", "Jett#NA1", "Omen#NA1", "Sage#NA1", "Phoenix#NA1", "Reyna#NA1",
    "Raze#NA1", "Breach#NA1", "Brimstone#NA1", "Cypher#NA1", "Sova#NA1", "Killjoy#NA1",
    "Skye#NA1", "Yoru#NA1", "Astra#NA1", "KAYO#NA1", "Chamber#NA1", "Neon#NA1",
    "Fade#NA1", "Harbor#NA1", "Gekko#NA1", "Deadlock#NA1", "Iso#NA1", "Clove#NA1",
    "Player#NA1", "Noob#NA1", "Pro#NA1", "God#NA1", "King#NA1", "Queen#NA1",
    "Sniper#NA1", "Faker#T1", "Deft#T1", "Keria#T1", "Gumayusi#T1", "Zeus#T1",
    "Oner#T1", "ShowMaker#DK", "Canyon#DK", "Chovy#GENG", "Ruler#JDG", "Kanavi#JDG",
    "Knight#JDG", "369#JDG", "Missing#JDG", "JackeyLove#TES", "Rookie#TES", "TheShy#WBG",
    "Doinb#FPX", "Scout#LNG", "Viper#HLE", "Zeka#HLE", "Kingen#HLE", "BeryL#DRX",
    "Pyosik#TL", "CoreJJ#TL", "Yeon#TL", "APA#TL", "Impact#TL", "Spica#FLY",
    "Vulcan#FLY", "Prince#FLY", "VicLa#FLY", "Ssumday#FLY", "Blaber#C9", "Fudge#C9",
    "Berserker#C9", "Zven#C9", "EMENES#C9", "Gori#GG", "River#GG", "huhi#GG",
    "Stixxay#GG", "Licorice#GG", "Jojopyun#EG", "Inspired#EG", "Ssumday#EG", "FBI#EG",
    "Vulcan#EG", "Danny#EG", "Doublelift#100T", "Bjergsen#100T", "Closer#100T", "Tenacity#100T",
    "Busio#100T", "Caps#G2", "Jankos#TH", "Perkz#VIT", "Rekkles#FNC", "Wunder#FNC",
    "Mikyx#G2", "HansSama#G2", "BrokenBlade#G2", "Yike#G2", "Elyoya#MAD", "Nisqy#MAD",
    "Carzzy#MAD", "Hylissang#MAD", "Chasy#MAD", "Larssen#KOI", "Comp#KOI", "Trymbi#KOI",
    "Malrang#KOI", "Szygenda#KOI", "Odoamne#EXC", "Vetheo#EXC", "Patrik#EXC", "Targamas#EXC",
    "Xerxe#EXC", "Bo#VIT", "Photon#VIT", "Upset#VIT", "Kaiser#VIT", "Neon#VIT",
    "Exakick#SK", "Markoon#SK", "Sertuss#SK", "Doss#SK", "Irrelevant#SK", "Crownie#BDS",
    "Sheo#BDS", "Adam#BDS", "Labrov#BDS", "Nuclearint#BDS", "Finn#AST", "113#AST",
    "Dajor#AST", "Kobbe#AST", "Jeonghoon#AST", "Evi#TH", "Ruby#TH", "Jackspektra#TH",
    "Mersa#TH", "S0m#NA1", "Tarik#NA1", "TenZ#NA1", "Kyedae#NA1", "Zekken#NA1",
    "Yay#NA1", "FNS#NA1", "Crashies#NA1", "Victor#NA1", "Marved#NA1", "Sick#NA1",
    "Dapr#NA1", "Shahzam#NA1", "Zombs#NA1", "Asuna#NA1", "Bang#NA1", "Cryo#NA1",
    "Derrek#NA1", "Stellar#NA1", "Nats#NA1", "Chronicle#NA1", "Boaster#NA1", "Derke#NA1",
    "Leo#NA1", "Alfajer#NA1", "ScreaM#NA1", "Nivera#NA1", "Jamppi#NA1", "Soulcas#NA1",
    "Koldamenta#NA1", "Avova#NA1", "Bonecold#NA1", "Starxo#NA1", "Cned#NA1", "Zeek#NA1"
]

async def seed_player_pool(db: AsyncSession):
    try:
        # Check if pool is already seeded
        result = await db.execute(select(PlayerStat))
        existing_count = len(result.scalars().all())
        
        if existing_count < 100:
            logger.info(f"Seeding database with {len(SEED_PLAYERS)} players...")
            for player_id in SEED_PLAYERS:
                # Assign a random MMR between 0 (Iron) and 3000 (Radiant)
                # This ensures the queue can always find 9 players close to ANY user's MMR
                random_mmr = random.uniform(0.0, 3000.0)
                
                # Check if already exists
                existing = await db.execute(select(PlayerStat).where(PlayerStat.player_id == player_id))
                if not existing.scalar_one_or_none():
                    stat = PlayerStat(
                        player_id=player_id,
                        puuid=f"seeded_{player_id}",
                        current_mmr=random_mmr,
                        match_count=0
                    )
                    db.add(stat)
            
            await db.commit()
            logger.info("Database successfully seeded with player pool!")
    except Exception as e:
        logger.error(f"Failed to seed player pool: {e}")
