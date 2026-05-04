from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import Question, UserProgress


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
        stmt = select(Question).where(Question.external_key == external_key)
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            existing.topic = topic
            existing.difficulty = difficulty
            existing.text = text
            existing.options = options
            existing.correct_index = correct_index
            existing.explanation = explanation
            existing.is_active = True
            await self.session.flush()
            return existing

        question = Question(
            external_key=external_key,
            topic=topic,
            difficulty=difficulty,
            text=text,
            options=options,
            correct_index=correct_index,
            explanation=explanation,
        )
        self.session.add(question)
        await self.session.flush()
        return question

    async def select_due_for_user(self, user_id: int, limit: int) -> list[Question]:
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
        new_questions = list((await self.session.execute(new_stmt)).scalars().all())
        return due_questions + new_questions
