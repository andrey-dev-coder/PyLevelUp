from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.db.models import (
    Attempt,
    Bookmark,
    DailyChallengeAttempt,
    MockSession,
    Question,
    User,
)
from pylevelup.repositories import AchievementRepository
from pylevelup.services.mastery import compute_level


async def _grant_codes(
    session: AsyncSession, user_id: int, codes: list[str]
) -> list[str]:
    if not codes:
        return []
    repo = AchievementRepository(session)
    existing = await repo.get_user_codes(user_id)
    new_codes: list[str] = []
    for code in codes:
        if code in existing:
            continue
        granted = await repo.grant(user_id, code)
        if granted:
            new_codes.append(code)
    return new_codes


async def _all_codes_for_user(session: AsyncSession, user_id: int) -> list[str]:
    user_obj = await session.get(User, user_id)
    if user_obj is None:
        return []

    codes: list[str] = []

    if user_obj.total_answered >= 1:
        codes.append("first_step")
    if user_obj.total_correct >= 10:
        codes.append("ten_correct")
    if user_obj.total_correct >= 100:
        codes.append("hundred_correct")
    if user_obj.total_correct >= 500:
        codes.append("five_hundred_correct")

    if user_obj.max_streak >= 3:
        codes.append("streak_3")
    if user_obj.max_streak >= 7:
        codes.append("streak_7")
    if user_obj.max_streak >= 30:
        codes.append("streak_30")

    mock_passed_stmt = select(func.count(MockSession.id)).where(
        MockSession.user_id == user_id, MockSession.passed.is_(True)
    )
    mock_passed_count = int((await session.execute(mock_passed_stmt)).scalar_one() or 0)
    if mock_passed_count >= 1:
        codes.append("mock_passed")

    mock_perfect_stmt = select(func.count(MockSession.id)).where(
        MockSession.user_id == user_id,
        MockSession.correct_count == MockSession.total_questions,
        MockSession.total_questions >= 20,
    )
    mock_perfect_count = int((await session.execute(mock_perfect_stmt)).scalar_one() or 0)
    if mock_perfect_count >= 1:
        codes.append("mock_perfect")

    daily_correct_stmt = select(func.count(DailyChallengeAttempt.id)).where(
        DailyChallengeAttempt.user_id == user_id,
        DailyChallengeAttempt.is_correct.is_(True),
    )
    daily_correct = int((await session.execute(daily_correct_stmt)).scalar_one() or 0)
    if daily_correct >= 5:
        codes.append("daily_5")
    if daily_correct >= 25:
        codes.append("daily_25")

    bookmarks_stmt = select(func.count(Bookmark.id)).where(Bookmark.user_id == user_id)
    bookmarks_count = int((await session.execute(bookmarks_stmt)).scalar_one() or 0)
    if bookmarks_count >= 10:
        codes.append("bookmarks_10")

    topic_stmt = (
        select(
            Question.topic.label("topic"),
            func.count(Attempt.id).label("answered"),
            func.sum(case((Attempt.is_correct.is_(True), 1), else_=0)).label("correct"),
        )
        .join(Question, Question.id == Attempt.question_id)
        .where(Attempt.user_id == user_id)
        .group_by(Question.topic)
    )
    topic_rows = (await session.execute(topic_stmt)).all()
    has_bronze = False
    has_gold = False
    has_diamond = False
    for row in topic_rows:
        answered = int(row.answered or 0)
        correct = int(row.correct or 0)
        accuracy = (correct / answered * 100.0) if answered else 0.0
        level = compute_level(answered, accuracy).code
        if level in ("bronze", "silver", "gold", "diamond"):
            has_bronze = True
        if level in ("gold", "diamond"):
            has_gold = True
        if level == "diamond":
            has_diamond = True
    if has_bronze:
        codes.append("topic_bronze")
    if has_gold:
        codes.append("topic_gold")
    if has_diamond:
        codes.append("topic_diamond")

    return codes


async def evaluate_and_grant(session: AsyncSession, user_id: int) -> list[str]:
    candidate_codes = await _all_codes_for_user(session, user_id)
    return await _grant_codes(session, user_id, candidate_codes)


__all__ = ["evaluate_and_grant"]
