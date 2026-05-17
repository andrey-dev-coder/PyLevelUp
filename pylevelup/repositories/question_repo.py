from datetime import UTC, datetime

from sqlalchemy import Text, cast, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import DailyChallenge, Question, UserProgress


class QuestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, question_id: int) -> Question | None:
        return await self.session.get(Question, question_id)

    async def get_many(self, ids: list[int]) -> list[Question]:
        if not ids:
            return []
        stmt = select(Question).where(Question.id.in_(ids))
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_active(self) -> int:
        stmt = select(func.count(Question.id)).where(Question.is_active.is_(True))
        return int((await self.session.execute(stmt)).scalar_one())

    async def upsert_external(
        self,
        external_key: str,
        topic: str,
        difficulty: int,
        text: str,
        options: list[str],
        correct_index: int,
        explanation: str | None,
    ) -> Question:
        stmt = pg_insert(Question).values(
            external_key=external_key,
            topic=topic,
            difficulty=difficulty,
            text=text,
            options=options,
            correct_index=correct_index,
            explanation=explanation,
            is_active=True,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Question.external_key],
            set_={
                "topic": stmt.excluded.topic,
                "difficulty": stmt.excluded.difficulty,
                "text": stmt.excluded.text,
                "options": stmt.excluded.options,
                "correct_index": stmt.excluded.correct_index,
                "explanation": stmt.excluded.explanation,
                "is_active": True,
            },
        ).returning(Question.id)
        result = await self.session.execute(stmt)
        question_id = result.scalar_one()
        await self.session.flush()
        question = await self.session.get(Question, question_id)
        if question is None:
            raise RuntimeError("question_upsert_failed")
        return question

    async def select_due_for_user(
        self,
        user_id: int,
        limit: int,
        topics: list[str] | None = None,
    ) -> list[Question]:
        now = datetime.now(UTC)
        due = (
            select(Question)
            .join(UserProgress, UserProgress.question_id == Question.id)
            .where(
                UserProgress.user_id == user_id,
                UserProgress.next_review_at <= now,
                Question.is_active.is_(True),
            )
            .order_by(UserProgress.next_review_at.asc())
            .limit(limit)
        )
        if topics:
            due = due.where(Question.topic.in_(topics))
        due_questions = list((await self.session.execute(due)).scalars().all())
        if len(due_questions) >= limit:
            return due_questions

        seen_subq = select(UserProgress.question_id).where(UserProgress.user_id == user_id)
        new_stmt = (
            select(Question)
            .where(Question.is_active.is_(True), Question.id.notin_(seen_subq))
            .order_by(Question.difficulty.asc(), func.random())
            .limit(limit - len(due_questions))
        )
        if topics:
            new_stmt = new_stmt.where(Question.topic.in_(topics))
        new_questions = list((await self.session.execute(new_stmt)).scalars().all())
        combined = due_questions + new_questions
        if len(combined) >= limit:
            return combined

        existing_ids = [q.id for q in combined]
        fallback = await self.random_active(
            limit=limit - len(combined),
            topics=topics,
            exclude_ids=existing_ids,
        )
        return combined + fallback

    async def random_active(
        self,
        limit: int,
        topics: list[str] | None,
        exclude_ids: list[int] | None = None,
    ) -> list[Question]:
        stmt = select(Question).where(Question.is_active.is_(True)).order_by(func.random()).limit(limit)
        if topics:
            stmt = stmt.where(Question.topic.in_(topics))
        if exclude_ids:
            stmt = stmt.where(Question.id.notin_(exclude_ids))
        return list((await self.session.execute(stmt)).scalars().all())

    async def search(self, query: str, limit: int = 10) -> list[Question]:
        if not query.strip():
            return []
        pattern = f"%{query.strip()}%"
        stmt = (
            select(Question)
            .where(Question.is_active.is_(True))
            .where(
                or_(
                    Question.text.ilike(pattern),
                    Question.explanation.ilike(pattern),
                    cast(Question.options, Text).ilike(pattern),
                )
            )
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def search_admin(
        self,
        query: str,
        topic: str | None = None,
        offset: int = 0,
        limit: int = 10,
    ) -> list[Question]:
        if not query.strip():
            return []
        pattern = f"%{query.strip()}%"
        stmt = select(Question).where(
            or_(
                Question.text.ilike(pattern),
                Question.explanation.ilike(pattern),
                cast(Question.options, Text).ilike(pattern),
            )
        )
        if topic is not None:
            stmt = stmt.where(Question.topic == topic)
        stmt = stmt.order_by(Question.id.asc()).offset(offset).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_search_admin(
        self,
        query: str,
        topic: str | None = None,
    ) -> int:
        if not query.strip():
            return 0
        pattern = f"%{query.strip()}%"
        stmt = select(func.count(Question.id)).where(
            or_(
                Question.text.ilike(pattern),
                Question.explanation.ilike(pattern),
                cast(Question.options, Text).ilike(pattern),
            )
        )
        if topic is not None:
            stmt = stmt.where(Question.topic == topic)
        return int((await self.session.execute(stmt)).scalar_one())

    async def list_by_topic(
        self,
        topic: str,
        offset: int = 0,
        limit: int = 10,
    ) -> list[Question]:
        stmt = (
            select(Question)
            .where(Question.topic == topic)
            .order_by(Question.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_by_topic(self, topic: str) -> int:
        stmt = select(func.count(Question.id)).where(Question.topic == topic)
        return int((await self.session.execute(stmt)).scalar_one())

    async def update_fields(
        self,
        question_id: int,
        *,
        text: str | None = None,
        options: list[str] | None = None,
        correct_index: int | None = None,
        explanation: str | None = None,
        difficulty: int | None = None,
    ) -> Question | None:
        question = await self.session.get(Question, question_id)
        if question is None:
            return None
        if text is not None:
            question.text = text
        if options is not None:
            question.options = options
        if correct_index is not None:
            question.correct_index = correct_index
        if explanation is not None:
            question.explanation = explanation
        if difficulty is not None:
            question.difficulty = difficulty
        await self.session.flush()
        return question

    async def set_active(self, question_id: int, active: bool) -> Question | None:
        question = await self.session.get(Question, question_id)
        if question is None:
            return None
        question.is_active = active
        await self.session.flush()
        return question

    async def delete_one(self, question_id: int) -> bool:
        await self.session.execute(
            delete(DailyChallenge).where(DailyChallenge.question_id == question_id)
        )
        result = await self.session.execute(
            delete(Question).where(Question.id == question_id)
        )
        await self.session.flush()
        return (result.rowcount or 0) > 0
