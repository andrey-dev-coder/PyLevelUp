from sqlalchemy import Text, cast, func, or_, select
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
        code: str | None = None,
        code_language: str | None = None,
    ) -> OpenQuestion:
        stmt = pg_insert(OpenQuestion).values(
            external_key=external_key,
            topic=topic,
            difficulty=difficulty,
            text=text,
            ideal_answer=ideal_answer,
            checklist=checklist,
            code=code,
            code_language=code_language,
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
                "code": stmt.excluded.code,
                "code_language": stmt.excluded.code_language,
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

    async def list_by_topic(
        self,
        topic: str,
        offset: int = 0,
        limit: int = 10,
    ) -> list[OpenQuestion]:
        stmt = (
            select(OpenQuestion)
            .where(OpenQuestion.topic == topic)
            .order_by(OpenQuestion.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_by_topic(self, topic: str) -> int:
        stmt = select(func.count(OpenQuestion.id)).where(OpenQuestion.topic == topic)
        return int((await self.session.execute(stmt)).scalar_one())

    async def update_fields(
        self,
        question_id: int,
        *,
        text: str | None = None,
        ideal_answer: str | None = None,
        checklist: list[str] | None = None,
        difficulty: int | None = None,
    ) -> "OpenQuestion | None":
        question = await self.session.get(OpenQuestion, question_id)
        if question is None:
            return None
        if text is not None:
            question.text = text
        if ideal_answer is not None:
            question.ideal_answer = ideal_answer
        if checklist is not None:
            question.checklist = checklist
        if difficulty is not None:
            question.difficulty = difficulty
        await self.session.flush()
        return question

    async def update_code(
        self,
        question_id: int,
        *,
        code: str | None,
    ) -> "OpenQuestion | None":
        question = await self.session.get(OpenQuestion, question_id)
        if question is None:
            return None
        question.code = code
        await self.session.flush()
        return question

    async def update_code_language(
        self,
        question_id: int,
        *,
        code_language: str | None,
    ) -> "OpenQuestion | None":
        question = await self.session.get(OpenQuestion, question_id)
        if question is None:
            return None
        question.code_language = code_language
        await self.session.flush()
        return question

    async def set_active(self, question_id: int, active: bool) -> "OpenQuestion | None":
        question = await self.session.get(OpenQuestion, question_id)
        if question is None:
            return None
        question.is_active = active
        await self.session.flush()
        return question

    async def delete_one(self, question_id: int) -> bool:
        from sqlalchemy import delete as _delete
        result = await self.session.execute(
            _delete(OpenQuestion).where(OpenQuestion.id == question_id)
        )
        await self.session.flush()
        return (result.rowcount or 0) > 0

    async def search_admin(
        self,
        query: str,
        topic: str | None = None,
        offset: int = 0,
        limit: int = 10,
    ) -> list[OpenQuestion]:
        if not query.strip():
            return []
        pattern = f"%{query.strip()}%"
        stmt = select(OpenQuestion).where(
            or_(
                OpenQuestion.text.ilike(pattern),
                OpenQuestion.ideal_answer.ilike(pattern),
                cast(OpenQuestion.checklist, Text).ilike(pattern),
            )
        )
        if topic is not None:
            stmt = stmt.where(OpenQuestion.topic == topic)
        stmt = stmt.order_by(OpenQuestion.id.asc()).offset(offset).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_search_admin(
        self,
        query: str,
        topic: str | None = None,
    ) -> int:
        if not query.strip():
            return 0
        pattern = f"%{query.strip()}%"
        stmt = select(func.count(OpenQuestion.id)).where(
            or_(
                OpenQuestion.text.ilike(pattern),
                OpenQuestion.ideal_answer.ilike(pattern),
                cast(OpenQuestion.checklist, Text).ilike(pattern),
            )
        )
        if topic is not None:
            stmt = stmt.where(OpenQuestion.topic == topic)
        return int((await self.session.execute(stmt)).scalar_one())
