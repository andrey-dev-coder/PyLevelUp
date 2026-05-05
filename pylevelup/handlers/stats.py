from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.categories import display_name
from pylevelup.keyboards import build_profile_keyboard
from pylevelup.repositories import AchievementRepository, UserRepository
from pylevelup.services import StatsService, UserStats
from pylevelup.services.achievements import ACHIEVEMENTS
from pylevelup.services.mastery import compute_level, next_level

router = Router(name="pylevelup_stats")


def _format_date(value) -> str:
    return value.strftime("%d.%m.%Y") if value else "-"


def _format_topics(stats: UserStats) -> str:
    if not stats.topics:
        return "Пока нет ответов в категориях. Запусти тренажёр - и здесь появятся проценты."
    lines = []
    for ts in stats.topics:
        name = display_name(ts.topic)
        level = compute_level(ts.answered, ts.accuracy_percent)
        upcoming = next_level(ts.answered, ts.accuracy_percent)
        line = (
            f"{level.icon} <b>{escape(name)}</b> [{level.label}]: "
            f"{ts.correct}/{ts.answered} ({ts.accuracy_percent}%)"
        )
        if upcoming is not None:
            need_answers = max(0, upcoming.min_answered - ts.answered)
            need_acc = max(0.0, upcoming.min_accuracy - ts.accuracy_percent)
            hints: list[str] = []
            if need_answers > 0:
                hints.append(f"+{need_answers} ответов")
            if need_acc > 0:
                hints.append(f"точность +{need_acc:.0f}%")
            if hints:
                line += f" - до {upcoming.label}: {', '.join(hints)}"
        lines.append(line)
    return "\n".join(lines)


def _format_profile(stats: UserStats | None, first_name: str | None, achievements_earned: int = 0) -> str:
    name = escape(first_name) if first_name else "коллега"
    if stats is None:
        return (
            f"<b>Профиль {name}</b>\n\n"
            "Здесь пока пусто. Жми /start или 'Начать тест', чтобы появились данные о визитах, "
            "стрике и точности по категориям."
        )
    header = (
        f"<b>Профиль {name}</b>\n"
        f"В системе с: <b>{_format_date(stats.member_since)}</b>\n"
        f"Последний визит: <b>{_format_date(stats.last_active_date)}</b>\n"
        f"Всего заходов в бота: <b>{stats.total_starts}</b>\n"
    )
    streaks = (
        "\n<b>Стрик</b>\n"
        f"Сейчас подряд дней: <b>{stats.current_streak}</b>\n"
        f"Максимум подряд: <b>{stats.max_streak}</b>\n"
    )
    if stats.total_answered == 0:
        body = (
            "\n<b>Ответы</b>\n"
            "Ещё не было пройденных вопросов в тренажёре. Открой 'Начать тест' - и здесь "
            "появится точность по каждой категории."
        )
        return header + streaks + body
    answers = (
        "\n<b>Ответы</b>\n"
        f"Правильно: <b>{stats.total_correct}</b> из <b>{stats.total_answered}</b>\n"
        f"Общая точность: <b>{stats.accuracy_percent}%</b>\n"
        f"Ошибок в копилке: <b>{stats.mistakes_count}</b>\n"
    )
    rank = (
        "\n<b>Рейтинг</b>\n"
        f"Место: <b>{stats.ranking_position}</b> из <b>{stats.total_users}</b>\n"
        f"Очки: <b>{stats.ranking_score}</b>\n"
    )
    achievements_block = (
        f"\n<b>Ачивки</b>: {achievements_earned}/{len(ACHIEVEMENTS)}\n"
    )
    by_topic = "\n<b>По категориям</b>\n" + _format_topics(stats)
    return header + streaks + answers + rank + achievements_block + by_topic


async def _send_profile(
    target: Message,
    telegram_id: int,
    first_name: str | None,
    session_factory: async_sessionmaker,
) -> None:
    async with session_factory() as db:
        user = await UserRepository(db).get_by_telegram_id(telegram_id)
        stats = None
        mistakes = 0
        achievements_earned = 0
        if user is not None:
            stats = await StatsService(db).get_user_stats(user.id)
            if stats is not None:
                mistakes = stats.mistakes_count
            earned = await AchievementRepository(db).get_user_codes(user.id)
            achievements_earned = len(earned)
    await target.answer(
        _format_profile(stats, first_name, achievements_earned),
        reply_markup=build_profile_keyboard(has_mistakes=mistakes > 0),
    )


@router.message(Command("stats"))
async def handle_stats(message: Message, session_factory: async_sessionmaker) -> None:
    if message.from_user is None:
        return
    await _send_profile(message, message.from_user.id, message.from_user.first_name, session_factory)


@router.callback_query(F.data == "stats:show")
async def handle_stats_callback(callback: CallbackQuery, session_factory: async_sessionmaker) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    await _send_profile(
        callback.message,
        callback.from_user.id,
        callback.from_user.first_name,
        session_factory,
    )
    await callback.answer()
