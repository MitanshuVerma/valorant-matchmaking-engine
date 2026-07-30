from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ARRAY
from sqlalchemy.sql import func
from app.db.postgres import Base

class Match(Base):
    __tablename__ = "matches"
    
    id = Column(Integer, primary_key=True, index=True)
    lobby_id = Column(String, unique=True, index=True)
    status = Column(String, default="formed")
    players = Column(JSON) # Store list of player info
    average_mmr = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PlayerStat(Base):
    __tablename__ = "player_stats"
    
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(String, index=True)
    puuid = Column(String, index=True, nullable=True)
    match_count = Column(Integer, default=0)
    current_mmr = Column(Float)
    avg_kda = Column(Float, nullable=True)
    avg_kp = Column(Float, nullable=True)
    avg_gpm = Column(Float, nullable=True)
    avg_cspm = Column(Float, nullable=True)
    last_updated = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
