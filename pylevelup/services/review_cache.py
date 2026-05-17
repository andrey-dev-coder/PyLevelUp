from __future__ import annotations

import orjson
from redis.asyncio import Redis


class ReviewCache:
    KEY_PREFIX = "pylevelup:review"
    DEFAULT_TTL_SECONDS = 60 * 60 * 24

    def __init__(self, redis: Redis, ttl_seconds: int | None = None) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds or self.DEFAULT_TTL_SECONDS

    def _key(self, user_id: int) -> str:
        return f"{self.KEY_PREFIX}:{user_id}"

    async def save(self, user_id: int, wrong_ids: list[int]) -> None:
        if not wrong_ids:
            await self.clear(user_id)
            return
        payload = orjson.dumps({"wrong_ids": wrong_ids}).decode()
        key = self._key(user_id)
        async with self.redis.pipeline(transaction=True) as pipe:
            await pipe.set(key, payload)
            await pipe.expire(key, self.ttl_seconds)
            await pipe.execute()

    async def load(self, user_id: int) -> list[int]:
        raw = await self.redis.get(self._key(user_id))
        if not raw:
            return []
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode()
        try:
            data = orjson.loads(raw)
        except orjson.JSONDecodeError:
            return []
        ids = data.get("wrong_ids") if isinstance(data, dict) else None
        if not isinstance(ids, list):
            return []
        return [int(i) for i in ids if isinstance(i, (int, str)) and str(i).lstrip("-").isdigit()]

    async def clear(self, user_id: int) -> None:
        await self.redis.delete(self._key(user_id))
