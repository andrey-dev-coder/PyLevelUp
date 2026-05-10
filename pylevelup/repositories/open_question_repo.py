from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import OpenQuestion


class OpenQuestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_active(self) -> int:
        stmt = select(func.count(OpenQuestion.id)).where(OpenQuestion.is_active.is_(True))
        return int((await self.session.execute(stmt)).scalar_one())

    async def random_active(
        self,
        topic: str | None = None,
        exclude_ids: list[int] | None = None,
    ) -> OpenQuestion | None:
        stmt = (
            select(OpenQuestion)
            .where(OpenQuestion.is_active.is_(True))
            .order_by(func.random())
            .limit(1)
        )
        if topic:
            stmt = stmt.where(OpenQuestion.topic == topic)
        if exclude_ids:
            stmt = stmt.where(OpenQuestion.id.notin_(exclude_ids))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get(self, question_id: int) -> OpenQuestion | None:
        return await self.session.get(OpenQuestion, question_id)

    async def upsert(
        self,
        external_key: str,
        topic: str,
        difficulty: int,
        text: str,
        ideal_answer: str,
        checklist: list[str] | None,
    ) -> OpenQuestion:
        stmt = pg_insert(OpenQuestion).values(
            external_key=external_key,
            topic=topic,
            difficulty=difficulty,
            text=text,
            ideal_answer=ideal_answer,
            checklist=checklist,
            is_active=True,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[OpenQuestion.external_key],
            set_={
                "topic": stmt.excluded.topic,
                "difficulty": stmt.excluded.difficulty,
                "text": stmt.excluded.text,
                "ideal_answer": stmt.excluded.ideal_answer,
                "checklist": stmt.excluded.checklist,
                "is_active": True,
            },
        ).returning(OpenQuestion.id)
        result = await self.session.execute(stmt)
        question_id = result.scalar_one()
        await self.session.flush()
        question = await self.session.get(OpenQuestion, question_id)
        if question is None:
            raise RuntimeError("open_question_upsert_failed")
        return question
