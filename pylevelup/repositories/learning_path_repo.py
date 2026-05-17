from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pylevelup.db.models import (
    LearningPath,
    LearningPathStep,
    UserLearningPathProgress,
)


class LearningPathRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_active(self) -> list[LearningPath]:
        stmt = (
            select(LearningPath)
            .where(LearningPath.is_active.is_(True))
            .options(selectinload(LearningPath.steps))
            .order_by(LearningPath.order_index.asc(), LearningPath.id.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_all(self) -> list[LearningPath]:
        stmt = (
            select(LearningPath)
            .options(selectinload(LearningPath.steps))
            .order_by(LearningPath.order_index.asc(), LearningPath.id.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get(self, path_id: int) -> LearningPath | None:
        stmt = (
            select(LearningPath)
            .where(LearningPath.id == path_id)
            .options(selectinload(LearningPath.steps))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> LearningPath | None:
        stmt = (
            select(LearningPath)
            .where(LearningPath.slug == slug)
            .options(selectinload(LearningPath.steps))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        slug: str,
        title: str,
        description: str | None = None,
        order_index: int = 0,
    ) -> LearningPath:
        path = LearningPath(
            slug=slug,
            title=title,
            description=description,
            order_index=order_index,
            is_active=True,
        )
        self.session.add(path)
        await self.session.flush()
        return path

    async def update(
        self,
        path_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
        order_index: int | None = None,
    ) -> LearningPath | None:
        path = await self.get(path_id)
        if path is None:
            return None
        if title is not None:
            path.title = title
        if description is not None:
            path.description = description
        if is_active is not None:
            path.is_active = is_active
        if order_index is not None:
            path.order_index = order_index
        await self.session.flush()
        return path

    async def delete(self, path_id: int) -> bool:
        path = await self.session.get(LearningPath, path_id)
        if path is None:
            return False
        await self.session.delete(path)
        await self.session.flush()
        return True

    async def add_step(
        self,
        path_id: int,
        topic_key: str,
        title: str | None = None,
        required_accuracy: int = 70,
        required_questions: int = 10,
    ) -> LearningPathStep:
        existing = await self.get(path_id)
        position = 0
        if existing is not None and existing.steps:
            position = max(s.position for s in existing.steps) + 1
        step = LearningPathStep(
            path_id=path_id,
            position=position,
            topic_key=topic_key,
            title=title,
            required_accuracy=required_accuracy,
            required_questions=required_questions,
        )
        self.session.add(step)
        await self.session.flush()
        return step

    async def delete_step(self, step_id: int) -> bool:
        step = await self.session.get(LearningPathStep, step_id)
        if step is None:
            return False
        await self.session.delete(step)
        await self.session.flush()
        return True


class UserPathProgressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int, path_id: int) -> UserLearningPathProgress | None:
        stmt = select(UserLearningPathProgress).where(
            UserLearningPathProgress.user_id == user_id,
            UserLearningPathProgress.path_id == path_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def ensure(self, user_id: int, path_id: int) -> UserLearningPathProgress:
        progress = await self.get(user_id, path_id)
        if progress is not None:
            return progress
        progress = UserLearningPathProgress(
            user_id=user_id,
            path_id=path_id,
            current_position=0,
        )
        self.session.add(progress)
        await self.session.flush()
        return progress

    async def advance(
        self,
        user_id: int,
        path_id: int,
        new_position: int,
        completed: bool,
    ) -> None:
        progress = await self.ensure(user_id, path_id)
        progress.current_position = new_position
        if completed and progress.completed_at is None:
            progress.completed_at = datetime.now(UTC)
        await self.session.flush()

    async def list_for_user(
        self, user_id: int
    ) -> list[UserLearningPathProgress]:
        stmt = select(UserLearningPathProgress).where(
            UserLearningPathProgress.user_id == user_id
        )
        return list((await self.session.execute(stmt)).scalars().all())
