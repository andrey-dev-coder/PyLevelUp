from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import QuestionReport


class QuestionReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: int, question_id: int, reason: str) -> QuestionReport:
        report = QuestionReport(
            user_id=user_id,
            question_id=question_id,
            reason=reason,
            status="open",
        )
        self.session.add(report)
        await self.session.flush()
        return report

    async def list_open(self, limit: int = 20, offset: int = 0) -> list[QuestionReport]:
        stmt = (
            select(QuestionReport)
            .where(QuestionReport.status == "open")
            .order_by(QuestionReport.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_open(self) -> int:
        stmt = select(func.count(QuestionReport.id)).where(QuestionReport.status == "open")
        return int((await self.session.execute(stmt)).scalar_one())

    async def get(self, report_id: int) -> QuestionReport | None:
        return await self.session.get(QuestionReport, report_id)

    async def resolve(self, report_id: int, status: str) -> QuestionReport | None:
        report = await self.session.get(QuestionReport, report_id)
        if report is None:
            return None
        report.status = status
        report.resolved_at = datetime.now(UTC)
        await self.session.flush()
        return report

    async def has_recent_for_user(
        self,
        user_id: int,
        question_id: int,
    ) -> bool:
        stmt = (
            select(QuestionReport.id)
            .where(
                QuestionReport.user_id == user_id,
                QuestionReport.question_id == question_id,
                QuestionReport.status == "open",
            )
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar() is not None
