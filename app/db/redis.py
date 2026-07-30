import redis.asyncio as redis
import fakeredis.aioredis as fakeredis
from app.config import settings
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

class RedisClientWrapper:
    def __init__(self):
        self._client = None
        self._is_fake = False

    async def get_client(self):
        if self._client is None:
            # Try connecting to real Redis
            real_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
                protocol=2,
                socket_timeout=1.0
            )
            try:
                await real_client.ping()
                self._client = real_client
                logger.info(f"Connected to real Redis at {settings.redis_host}:{settings.redis_port}")
            except Exception as e:
                logger.warning(f"Could not connect to Redis ({e}). Falling back to in-memory FakeRedis.")
                self._client = fakeredis.FakeRedis(decode_responses=True)
                self._is_fake = True
        return self._client

    async def close(self):
        if self._client and not self._is_fake:
            await self._client.close()

redis_wrapper = RedisClientWrapper()

# Helper proxy functions
async def zadd_player(queue_name: str, mmr: float, payload: dict):
    client = await redis_wrapper.get_client()
    mapping = {json.dumps(payload): mmr}
    await client.zadd(queue_name, mapping)

async def zrem_player(queue_name: str, payload_str: str):
    client = await redis_wrapper.get_client()
    await client.zrem(queue_name, payload_str)

async def get_queue_range(queue_name: str, start: int = 0, end: int = -1, withscores: bool = True):
    client = await redis_wrapper.get_client()
    return await client.zrange(queue_name, start, end, withscores=withscores)

async def set_cache(key: str, value: Any, ttl: int = 300):
    client = await redis_wrapper.get_client()
    await client.set(key, json.dumps(value), ex=ttl)

async def get_cache(key: str) -> Optional[Any]:
    client = await redis_wrapper.get_client()
    val = await client.get(key)
    if val:
        return json.loads(val)
    return None
