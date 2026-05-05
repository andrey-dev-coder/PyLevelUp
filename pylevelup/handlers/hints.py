import random
from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.repositories import QuestionRepository, UserRepository
from pylevelup.services.test_session_service import TestSessionService

router = Router(name="pylevelup_hints")

DAILY_HINT_LIMIT = 3


def _today() -> datetime:
    return datetime.now(UTC).date()


@router.callback_query(F.data == "hint:dim")
async def handle_hint_dim(call: CallbackQuery) -> None:
    await call.answer("Этот вариант скрыт подсказкой 50/50", show_alert=False)


@router.callback_query(F.data.startswith("hint:5050:"))
async def handle_hint_5050(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    session_service: TestSessionService,
) -> None:
    if call.from_user is None or call.message is None or call.data is None:
        await call.answer()
        return
    parts = call.data.split(":", 2)
    if len(parts) != 3 or not parts[2].isdigit():
        await call.answer()
        return
    question_id = int(parts[2])

    async with session_factory() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_telegram_id(call.from_user.id)
        if user is None:
            await call.answer("Сначала /start", show_alert=True)
            return
        consumed, remaining = await user_repo.consume_hint(user.id, _today())
        await db.commit()

    if not consumed:
        await call.answer(
            f"Подсказки кончились - получишь {DAILY_HINT_LIMIT} новых завтра.",
            show_alert=True,
        )
        return

    async with session_factory() as db:
        question = await QuestionRepository(db).get_by_id(question_id)
    if question is None or not question.options:
        await call.answer("Вопрос недоступен", show_alert=True)
        return

    options_count = len(question.options)
    correct_index = question.correct_index
    wrong_indices = [i for i in range(options_count) if i != correct_index]
    if len(wrong_indices) < 2:
        await call.answer("Недостаточно вариантов для подсказки", show_alert=True)
        return
    to_hide = set(random.sample(wrong_indices, 2))

    current_markup = call.message.reply_markup
    if current_markup is None:
        await call.answer("Клавиатура недоступна", show_alert=True)
        return
    new_rows: list[list[InlineKeyboardButton]] = []
    for row in current_markup.inline_keyboard:
        new_row: list[InlineKeyboardButton] = []
        for btn in row:
            cd = btn.callback_data or ""
            if cd.startswith(f"ans:{question_id}:"):
                tail = cd.rsplit(":", 1)[-1]
                if tail.isdigit() and int(tail) in to_hide:
                    new_row.append(
                        InlineKeyboardButton(text="✗", callback_data="hint:dim")
                    )
                    continue
            if cd.startswith("hint:5050:"):
                continue
            new_row.append(btn)
        if new_row:
            new_rows.append(new_row)

    try:
        await call.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=new_rows)
        )
    except Exception:
        pass

    await call.answer(
        f"Убрал 2 неправильных варианта. Осталось подсказок: {remaining}",
        show_alert=True,
    )

    _ = session_service


__all__ = ["router"]
