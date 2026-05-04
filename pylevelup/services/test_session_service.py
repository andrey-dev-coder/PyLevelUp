from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pylevelup.config import Settings
from pylevelup.repositories import (
    AttemptRepository,
    DailySessionRepository,
    ProgressRepository,
    QuestionRepository,
    UserRepository,
)
from pylevelup.services.session_cache import RedisSessionCache, SessionCacheState
from pylevelup.services.spaced_repetition import SpacedRepetitionEngine


@dataclass
class StartSessionResult:
    state: SessionCacheState
    questions: dict[int, tuple[str, list[str], int]]


class TestSessionService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        cache: RedisSessionCache,
        engine: SpacedRepetitionEngine,
        settings: Settings,
    ) -> None:
        self.session_factory = session_factory
        self.cache = cache
        self.engine = engine
        self.settings = settings

    REFILL_BATCH = 10

    async def start_session(
        self,
        telegram_user,
        topics: list[str] | None = None,
        target_total: int | None = None,
        is_unlimited: bool = False,
        counts_toward_daily: bool = True,
    ) -> StartSessionResult | None:
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

            if counts_toward_daily and not is_unlimited:
                already_today = await DailySessionRepository(db).get(user_id, date.today())
                used_today = already_today.questions_answered if already_today else 0
                remaining_today = self.settings.daily_question_limit - used_today
                if remaining_today <= 0:
                    await db.commit()
                    return None
                effective_target = (
                    min(target_total, remaining_today) if target_total else remaining_today
                )
            else:
                effective_target = target_total

            initial_limit = (
                effective_target if effective_target is not None else self.REFILL_BATCH
            )
            questions = await questions_repo.select_due_for_user(
                user_id, initial_limit, topics=topics
            )
            payloads = {q.id: (q.text, list(q.options), q.correct_index) for q in questions}
            queue = [q.id for q in questions]
            await db.commit()

        if not queue:
            return None

        cache_state = SessionCacheState(
            user_id=user_id,
            session_date=date.today(),
            queue=queue,
            current_index=0,
            answered=0,
            correct=0,
            topic_filter=topics,
            is_unlimited=is_unlimited,
            target_total=effective_target if not is_unlimited else None,
            counts_toward_daily=counts_toward_daily,
            last_question_sent_at=datetime.now(UTC),
        )
        await self.cache.save(cache_state)
        return StartSessionResult(state=cache_state, questions=payloads)

    async def refill_queue_if_needed(
        self, state: SessionCacheState
    ) -> tuple[SessionCacheState, dict[int, tuple[str, list[str], int]]]:
        if not state.needs_refill():
            return state, {}
        async with self.session_factory() as db:
            questions_repo = QuestionRepository(db)
            extra = await questions_repo.random_active(
                limit=self.REFILL_BATCH,
                topics=state.topic_filter,
                exclude_ids=state.queue,
            )
            if not extra:
                extra = await questions_repo.random_active(
                    limit=self.REFILL_BATCH,
                    topics=state.topic_filter,
                )
        payloads = {q.id: (q.text, list(q.options), q.correct_index) for q in extra}
        state.queue.extend(q.id for q in extra)
        await self.cache.save(state)
        return state, payloads

    async def get_question_payload(self, question_id: int) -> tuple[str, list[str], int] | None:
        async with self.session_factory() as db:
            question = await QuestionRepository(db).get_by_id(question_id)
            if question is None:
                return None
            return question.text, list(question.options), question.correct_index

    async def submit_answer(
        self,
        state: SessionCacheState,
        question_id: int,
        chosen_index: int,
        correct_index: int,
        response_time_ms: int,
    ) -> SessionCacheState:
        is_correct = chosen_index == correct_index
        quality = self.engine.quality_from_outcome(is_correct, response_time_ms)
        return await self.cache.record_answer(
            state=state,
            question_id=question_id,
            is_correct=is_correct,
            quality=quality,
            response_time_ms=response_time_ms,
        )

    async def flush_session(self, user_id: int, mark_finished: bool) -> None:
        state = await self.cache.load(user_id)
        if state is None:
            return
        if not state.pending and not mark_finished:
            return

        is_done = mark_finished or (not state.is_unlimited and state.remaining() == 0)

        async with self.session_factory() as db:
            await self._flush_pending(db, state)
            if state.counts_toward_daily:
                sessions_repo = DailySessionRepository(db)
                await sessions_repo.upsert(
                    user_id=state.user_id,
                    session_date=state.session_date,
                    questions_answered=state.answered,
                    correct_count=state.correct,
                    finished=is_done,
                )
                if is_done:
                    users = UserRepository(db)
                    await users.update_streak_after_session(state.user_id, state.session_date)
            await db.commit()

        if is_done:
            await self.cache.clear(user_id)
        else:
            state.pending = []
            await self.cache.save(state)

    async def _flush_pending(self, db: AsyncSession, state: SessionCacheState) -> None:
        if not state.pending:
            return
        attempts_repo = AttemptRepository(db)
        progress_repo = ProgressRepository(db)
        users = UserRepository(db)

        records: list[dict[str, object]] = []
        correct_delta = 0
        for answer in state.pending:
            records.append(
                {
                    "user_id": state.user_id,
                    "question_id": answer.question_id,
                    "is_correct": answer.is_correct,
                    "quality": answer.quality,
                    "response_time_ms": answer.response_time_ms,
                    "answered_at": answer.answered_at,
                    "session_date": state.session_date,
                }
            )
            if answer.is_correct:
                correct_delta += 1

        await attempts_repo.bulk_insert(records)

        for answer in state.pending:
            existing = await progress_repo.get(state.user_id, answer.question_id)
            new_state = self.engine.evaluate(
                prior_ease=existing.ease_factor if existing else None,
                prior_interval_days=existing.interval_days if existing else None,
                prior_repetitions=existing.repetitions if existing else None,
                quality=answer.quality,
                now=answer.answered_at,
            )
            await progress_repo.upsert(
                user_id=state.user_id,
                question_id=answer.question_id,
                ease_factor=new_state.ease_factor,
                interval_days=new_state.interval_days,
                repetitions=new_state.repetitions,
                next_review_at=new_state.next_review_at,
                last_quality=answer.quality,
            )

        await users.increment_totals(
            user_id=state.user_id,
            correct_delta=correct_delta,
            answered_delta=len(state.pending),
        )
