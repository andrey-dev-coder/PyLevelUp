from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import orjson
from redis.asyncio import Redis


@dataclass
class PendingAnswer:
    question_id: int
    is_correct: bool
    quality: int
    response_time_ms: int
    answered_at: datetime


@dataclass
class SessionCacheState:
    user_id: int
    session_date: date
    queue: list[int]
    current_index: int
    answered: int
    correct: int
    topic_filter: list[str] | None = None
    is_unlimited: bool = False
    target_total: int | None = None
    counts_toward_daily: bool = True
    pending: list[PendingAnswer] = field(default_factory=list)
    last_question_sent_at: datetime | None = None
    correct_streak: int = 0
    wrong_streak: int = 0
    current_difficulty: int = 2

    def remaining(self) -> int:
        if self.is_unlimited:
            return max(0, len(self.queue) - self.current_index)
        if self.target_total is None:
            return max(0, len(self.queue) - self.current_index)
        return max(0, self.target_total - self.answered)

    def needs_refill(self, threshold: int = 1) -> bool:
        return self.is_unlimited and (len(self.queue) - self.current_index) <= threshold

    def current_question_id(self) -> int | None:
        if self.current_index >= len(self.queue):
            return None
        return self.queue[self.current_index]

    def to_redis(self) -> dict[str, str]:
        return {
            "state": orjson.dumps(
                {
                    "user_id": self.user_id,
                    "session_date": self.session_date.isoformat(),
                    "queue": self.queue,
                    "current_index": self.current_index,
                    "answered": self.answered,
                    "correct": self.correct,
                    "topic_filter": self.topic_filter,
                    "is_unlimited": self.is_unlimited,
                    "target_total": self.target_total,
                    "counts_toward_daily": self.counts_toward_daily,
                    "last_question_sent_at": (
                        self.last_question_sent_at.isoformat()
                        if self.last_question_sent_at
                        else None
                    ),
                    "correct_streak": self.correct_streak,
                    "wrong_streak": self.wrong_streak,
                    "current_difficulty": self.current_difficulty,
                }
            ).decode(),
            "pending": orjson.dumps(
                [
                    {
                        "question_id": p.question_id,
                        "is_correct": p.is_correct,
                        "quality": p.quality,
                        "response_time_ms": p.response_time_ms,
                        "answered_at": p.answered_at.isoformat(),
                    }
                    for p in self.pending
                ]
            ).decode(),
        }

    @classmethod
    def from_redis(cls, payload: dict[str, str]) -> SessionCacheState:
        state = orjson.loads(payload["state"])
        pending_raw = orjson.loads(payload.get("pending", "[]"))
        pending = [
            PendingAnswer(
                question_id=p["question_id"],
                is_correct=p["is_correct"],
                quality=p["quality"],
                response_time_ms=p["response_time_ms"],
                answered_at=datetime.fromisoformat(p["answered_at"]),
            )
            for p in pending_raw
        ]
        last_sent = state.get("last_question_sent_at")
        return cls(
            user_id=state["user_id"],
            session_date=date.fromisoformat(state["session_date"]),
            queue=list(state["queue"]),
            current_index=state["current_index"],
            answered=state["answered"],
            correct=state["correct"],
            topic_filter=state.get("topic_filter"),
            is_unlimited=bool(state.get("is_unlimited", False)),
            target_total=state.get("target_total"),
            counts_toward_daily=bool(state.get("counts_toward_daily", True)),
            pending=pending,
            last_question_sent_at=datetime.fromisoformat(last_sent) if last_sent else None,
            correct_streak=int(state.get("correct_streak", 0)),
            wrong_streak=int(state.get("wrong_streak", 0)),
            current_difficulty=int(state.get("current_difficulty", 2)),
        )


class RedisSessionCache:
    KEY_PREFIX = "pylevelup:session"

    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    def _key(self, user_id: int) -> str:
        return f"{self.KEY_PREFIX}:{user_id}"

    async def load(self, user_id: int) -> SessionCacheState | None:
        raw = await self.redis.hgetall(self._key(user_id))
        if not raw:
            return None
        decoded = {
            (k.decode() if isinstance(k, (bytes, bytearray)) else k): (
                v.decode() if isinstance(v, (bytes, bytearray)) else v
            )
            for k, v in raw.items()
        }
        if "state" not in decoded:
            return None
        return SessionCacheState.from_redis(decoded)

    async def save(self, state: SessionCacheState) -> None:
        key = self._key(state.user_id)
        payload = state.to_redis()
        async with self.redis.pipeline(transaction=True) as pipe:
            await pipe.delete(key)
            await pipe.hset(key, mapping=payload)
            await pipe.expire(key, self.ttl_seconds)
            await pipe.execute()

    async def clear(self, user_id: int) -> None:
        await self.redis.delete(self._key(user_id))

    async def record_answer(
        self,
        state: SessionCacheState,
        question_id: int,
        is_correct: bool,
        quality: int,
        response_time_ms: int,
    ) -> SessionCacheState:
        state.pending.append(
            PendingAnswer(
                question_id=question_id,
                is_correct=is_correct,
                quality=quality,
                response_time_ms=response_time_ms,
                answered_at=datetime.now(UTC),
            )
        )
        state.answered += 1
        if is_correct:
            state.correct += 1
            state.correct_streak += 1
            state.wrong_streak = 0
        else:
            state.wrong_streak += 1
            state.correct_streak = 0
        if state.correct_streak >= 3:
            state.current_difficulty = min(5, state.current_difficulty + 1)
            state.correct_streak = 0
        elif state.wrong_streak >= 2:
            state.current_difficulty = max(1, state.current_difficulty - 1)
            state.wrong_streak = 0
        state.current_index += 1
        await self.save(state)
        return state
