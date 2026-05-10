from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass

from sqlalchemy import select, update

from pylevelup.ai import AIClient, AIError, AIUnavailable
from pylevelup.config import get_settings
from pylevelup.db.models import Question
from pylevelup.db.session import create_async_engine_instance, create_async_sessionmaker
from pylevelup.logger import configure_logging, get_logger
from pylevelup.utils.text import clean_text

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "Ты эксперт по Python и backend. На вход - вопрос с 4 вариантами ответа и индекс правильного. "
    "Для КАЖДОГО варианта дай короткое объяснение (1-2 предложения, по делу, без воды): "
    "почему правильный - верен, почему каждый неверный - неверен. "
    "Отвечай строго в JSON-формате без markdown, без префиксов, без лишних слов: "
    '{"explanations": ["объяснение варианта 1", "объяснение варианта 2", "..."]}. '
    "Массив длиной ровно по числу вариантов, по индексу."
)

JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class GenStats:
    total: int = 0
    skipped: int = 0
    success: int = 0
    failed: int = 0


def _build_prompt(question: Question) -> str:
    lines: list[str] = [
        f"Вопрос: {clean_text(question.text)}",
        "",
        "Варианты:",
    ]
    for idx, opt in enumerate(question.options):
        lines.append(f"{idx + 1}. {clean_text(opt)}")
    lines.append("")
    lines.append(f"Правильный вариант (1-based): {question.correct_index + 1}")
    if question.explanation:
        lines.append(f"Текущее общее объяснение: {clean_text(question.explanation)}")
    lines.append("")
    lines.append(
        "Дай объяснения по каждому варианту в JSON формате как описано в инструкции."
    )
    return "\n".join(lines)


def _parse_json(text: str, expected_len: int) -> list[str] | None:
    match = JSON_BLOCK_RE.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    explanations = payload.get("explanations") if isinstance(payload, dict) else None
    if not isinstance(explanations, list):
        return None
    if len(explanations) != expected_len:
        return None
    cleaned: list[str] = []
    for item in explanations:
        if not isinstance(item, str):
            return None
        cleaned.append(item.strip())
    return cleaned


def _needs_generation(question: Question) -> bool:
    if not question.options:
        return False
    existing = question.option_explanations
    if not existing:
        return True
    if len(existing) != len(question.options):
        return True
    return any(not (s or "").strip() for s in existing)


async def _generate_for_question(
    client: AIClient,
    question: Question,
    prefer: str,
) -> list[str] | None:
    prompt = _build_prompt(question)
    try:
        result = await client.generate(
            prompt,
            system=SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=900,
            prefer=prefer,
        )
    except (AIError, AIUnavailable) as exc:
        logger.warning(
            "generate_failed", question_id=question.id, error=str(exc)[:200]
        )
        return None
    explanations = _parse_json(result.text, len(question.options))
    if explanations is None:
        logger.warning(
            "parse_failed",
            question_id=question.id,
            provider=result.provider,
            raw=result.text[:300],
        )
    return explanations


async def _run(limit: int | None, topic: str | None, prefer: str, sleep_ms: int) -> GenStats:
    settings = get_settings()
    client = AIClient(settings)
    if not client.is_available():
        raise SystemExit("AI client not configured - set GEMINI_API_KEY or DEEPSEEK_API_KEY")
    engine = create_async_engine_instance(settings.database_url)
    sessionmaker = create_async_sessionmaker(engine)
    stats = GenStats()
    try:
        async with sessionmaker() as db:
            stmt = select(Question).where(Question.is_active.is_(True))
            if topic:
                stmt = stmt.where(Question.topic == topic)
            stmt = stmt.order_by(Question.id.asc())
            questions = list((await db.execute(stmt)).scalars().all())
        targets = [q for q in questions if _needs_generation(q)]
        stats.total = len(targets)
        if limit is not None:
            targets = targets[:limit]
        logger.info("generation_plan", candidates=stats.total, will_process=len(targets))
        for question in targets:
            if not _needs_generation(question):
                stats.skipped += 1
                continue
            explanations = await _generate_for_question(client, question, prefer)
            if explanations is None:
                stats.failed += 1
            else:
                async with sessionmaker() as db:
                    await db.execute(
                        update(Question)
                        .where(Question.id == question.id)
                        .values(option_explanations=explanations)
                    )
                    await db.commit()
                stats.success += 1
                logger.info(
                    "generated",
                    question_id=question.id,
                    topic=question.topic,
                    success=stats.success,
                    failed=stats.failed,
                )
            if sleep_ms > 0:
                await asyncio.sleep(sleep_ms / 1000)
    finally:
        await engine.dispose()
    return stats


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Bulk-generate option_explanations via AI")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N questions")
    parser.add_argument("--topic", type=str, default=None, help="Only this topic")
    parser.add_argument(
        "--prefer",
        type=str,
        default="deepseek",
        choices=["gemini", "deepseek"],
        help="Primary provider",
    )
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=4500,
        help="Delay between requests (Gemini free tier ~15 req/min => 4500ms safe)",
    )
    args = parser.parse_args()
    stats = asyncio.run(_run(args.limit, args.topic, args.prefer, args.sleep_ms))
    logger.info(
        "generation_done",
        total=stats.total,
        success=stats.success,
        skipped=stats.skipped,
        failed=stats.failed,
    )


if __name__ == "__main__":
    main()
