from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import asyncio
import os
from contextlib import asynccontextmanager

from app.db.redis import redis_wrapper
from app.db.postgres import engine, Base
from app.api import queue, player, ws
from app.core.queue import matchmaking_worker

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # Start the matchmaking background worker
    worker_task = asyncio.create_task(matchmaking_worker())
    
    yield
    
    # Shutdown
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    
    await redis_wrapper.close()
    await engine.dispose()

app = FastAPI(
    title="VALORANT Matchmaking Engine & Live Telemetry",
    description="Low-latency 5v5 matchmaking engine and AI player simulator",
    version="2.0.0",
    lifespan=lifespan
)

# Routers
app.include_router(queue.router, prefix="/api/v1/queue", tags=["Queue"])
app.include_router(player.router, prefix="/api/v1/player", tags=["Player Telemetry"])
app.include_router(ws.router, tags=["WebSockets"])

# Serve Static Frontend Files
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "VALORANT Matchmaking API is active. Go to /docs for API documentation."}

@app.get("/health")
async def health_check():
    return {"status": "ok"}
