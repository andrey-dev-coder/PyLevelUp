from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from pylevelup.ai.client import AIClient, AIError, AIResult, AIUnavailable
from pylevelup.config import Settings
from pylevelup.db.models import Question
from pylevelup.repositories import AIUsageRepository
from pylevelup.utils.text import clean_text

SYSTEM_PROMPT = (
    "Ты - наставник по Python-разработке и техническим собеседованиям. "
    "Отвечай по-русски, без воды, конкретно и по делу. "
    "Если уместно - дай короткий пример кода в тройных бэктиках (```python). "
    "Не пиши вступительных фраз вроде 'отличный вопрос', сразу переходи к сути. "
    "Длина ответа - 1-3 коротких абзаца, максимум 1500 символов."
)


def _format_question_block(question: Question, chosen_index: int | None) -> str:
    parts: list[str] = [
        f"Вопрос: {clean_text(question.text)}",
        "",
        "Варианты ответа:",
    ]
    for idx, option in enumerate(question.options):
        marker = "(правильный)" if idx == question.correct_index else ""
        if chosen_index is not None and idx == chosen_index and idx != question.correct_index:
            marker = "(выбран пользователем, неверный)"
        parts.append(f"{idx + 1}. {clean_text(option)} {marker}".strip())
    if question.explanation:
        parts.append("")
        parts.append(f"Текущее краткое объяснение: {clean_text(question.explanation)}")
    return "\n".join(parts)


async def elaborate_question(
    client: AIClient,
    question: Question,
    chosen_index: int | None = None,
) -> AIResult:
    user_prompt = (
        _format_question_block(question, chosen_index)
        + "\n\nРазверни объяснение: почему правильный ответ верен, "
        "и (если есть выбранный неверный) почему ошибочный вариант не подходит. "
        "Добавь короткое доп. знание по теме, чтобы пользователь лучше запомнил."
    )
    return await client.generate(user_prompt, system=SYSTEM_PROMPT, prefer="gemini")


async def free_form_answer(client: AIClient, question_text: str) -> AIResult:
    return await client.generate(question_text.strip(), system=SYSTEM_PROMPT, prefer="gemini")


async def check_quota(
    session: AsyncSession,
    settings: Settings,
    user_id: int,
    is_owner: bool,
) -> tuple[bool, int]:
    if is_owner:
        return True, settings.ai_daily_limit_per_user
    used = await AIUsageRepository(session).count_today(user_id)
    return used < settings.ai_daily_limit_per_user, settings.ai_daily_limit_per_user - used


async def record_usage(
    session: AsyncSession,
    user_id: int,
    kind: str,
    result: AIResult,
) -> None:
    await AIUsageRepository(session).record(
        user_id=user_id,
        kind=kind,
        provider=result.provider,
        model=result.model,
    )


__all__ = [
    "AIClient",
    "AIError",
    "AIResult",
    "AIUnavailable",
    "check_quota",
    "elaborate_question",
    "free_form_answer",
    "record_usage",
]
