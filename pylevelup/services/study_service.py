from __future__ import annotations

from dataclasses import dataclass

import orjson
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pylevelup.repositories import QuestionRepository, UserRepository


@dataclass
class StudyState:
    user_id: int
    topic_filter: list[str] | None
    queue: list[int]
    current_index: int

    def current_question_id(self) -> int | None:
        if self.current_index >= len(self.queue):
            return None
        return self.queue[self.current_index]


@dataclass
class StudyCard:
    question_id: int
    text: str
    options: list[str]
    correct_index: int
    explanation: str | None
    position: int
    total: int


class StudyService:
    KEY_PREFIX = "pylevelup:study"
    BATCH_SIZE = 50

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis,
        ttl_seconds: int,
    ) -> None:
        self.session_factory = session_factory
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    def _key(self, user_id: int) -> str:
        return f"{self.KEY_PREFIX}:{user_id}"

    async def _save(self, state: StudyState) -> None:
        payload = orjson.dumps(
            {
                "user_id": state.user_id,
                "topic_filter": state.topic_filter,
                "queue": state.queue,
                "current_index": state.current_index,
            }
        ).decode()
        await self.redis.set(self._key(state.user_id), payload, ex=self.ttl_seconds)

    async def _load(self, user_id: int) -> StudyState | None:
        raw = await self.redis.get(self._key(user_id))
        if raw is None:
            return None
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode()
        data = orjson.loads(raw)
        return StudyState(
            user_id=data["user_id"],
            topic_filter=data.get("topic_filter"),
            queue=list(data["queue"]),
            current_index=int(data["current_index"]),
        )

    async def clear(self, user_id: int) -> None:
        await self.redis.delete(self._key(user_id))

    async def start(self, telegram_user, topics: list[str] | None) -> StudyCard | None:
        async with self.session_factory() as db:
            users = UserRepository(db)
            user = await users.upsert_from_telegram(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                language_code=telegram_user.language_code,
            )
            user_id = user.id
            questions_repo = QuestionRepository(db)
            questions = await questions_repo.random_active(
                limit=self.BATCH_SIZE,
                topics=topics,
            )
            await db.commit()

        if not questions:
            return None

        state = StudyState(
            user_id=user_id,
            topic_filter=topics,
            queue=[q.id for q in questions],
            current_index=0,
        )
        await self._save(state)
        first = questions[0]
        return StudyCard(
            question_id=first.id,
            text=first.text,
            options=list(first.options),
            correct_index=first.correct_index,
            explanation=first.explanation,
            position=1,
            total=len(state.queue),
        )

    async def next_card(self, user_id: int) -> StudyCard | None:
        state = await self._load(user_id)
        if state is None:
            return None
        state.current_index += 1
        if state.current_index >= len(state.queue):
            await self._refill(state)
            if state.current_index >= len(state.queue):
                await self.clear(user_id)
                return None
        await self._save(state)
        return await self._build_card(state)

    async def current_card(self, user_id: int) -> StudyCard | None:
        state = await self._load(user_id)
        if state is None:
            return None
        return await self._build_card(state)

    async def _refill(self, state: StudyState) -> None:
        async with self.session_factory() as db:
            questions_repo = QuestionRepository(db)
            extra = await questions_repo.random_active(
                limit=self.BATCH_SIZE,
                topics=state.topic_filter,
                exclude_ids=state.queue,
            )
            if not extra:
                extra = await questions_repo.random_active(
                    limit=self.BATCH_SIZE,
                    topics=state.topic_filter,
                )
        if extra:
            state.queue.extend(q.id for q in extra)

    async def _build_card(self, state: StudyState) -> StudyCard | None:
        question_id = state.current_question_id()
        if question_id is None:
            return None
        async with self.session_factory() as db:
            question = await QuestionRepository(db).get_by_id(question_id)
        if question is None:
            return None
        return StudyCard(
            question_id=question.id,
            text=question.text,
            options=list(question.options),
            correct_index=question.correct_index,
            explanation=question.explanation,
            position=state.current_index + 1,
            total=len(state.queue),
        )
