from datetime import UTC, datetime
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from pylevelup.categories import (
    ALL_CATEGORY_KEY,
    CATEGORY_BY_KEY,
    SESSION_MODES,
    display_name,
    list_topic_filter,
)
from pylevelup.keyboards import (
    build_answer_keyboard,
    build_category_keyboard,
    build_finish_keyboard,
    build_main_menu,
    build_mode_keyboard,
    build_post_answer_keyboard,
    build_purpose_keyboard,
)
from pylevelup.repositories import BookmarkRepository, QuestionRepository, UserRepository
from pylevelup.services.achievement_evaluator import evaluate_and_grant
from pylevelup.services.achievement_notify import notify_user_about_codes
from pylevelup.services.test_session_service import TestSessionService
from pylevelup.states import TestStates
from pylevelup.utils.edit import edit_or_send, safe_edit_text
from pylevelup.utils.text import clean_text, format_question_text, render_with_code

router = Router(name="pylevelup_test")

ALGORITHMS_KEY = "algorithms"


async def _user_id(session_service: TestSessionService, telegram_id: int) -> int:
    async with session_service.session_factory() as db:
        user = await UserRepository(db).get_by_telegram_id(telegram_id)
        if user is None:
            raise RuntimeError("user not found")
        return user.id


async def _is_bookmarked(
    session_service: TestSessionService, user_id: int, question_id: int
) -> bool:
    async with session_service.session_factory() as db:
        return await BookmarkRepository(db).is_bookmarked(user_id, question_id)


async def _send_current_question(
    message: Message,
    telegram_id: int,
    session_service: TestSessionService,
    state: FSMContext,
) -> None:
    user_id = await _user_id(session_service, telegram_id)
    cache_state = await session_service.cache.load(user_id)
    if cache_state is None:
        await message.answer(
            "Сессия не найдена. Запусти заново через /test.",
            reply_markup=build_main_menu(),
        )
        await state.clear()
        return

    cache_state, _new_payloads = await session_service.refill_queue_if_needed(cache_state)
    question_id = cache_state.current_question_id()
    if question_id is None:
        await _finish(message, session_service, state, cache_state.user_id, by_user=False)
        return

    payload = await session_service.get_question_payload(question_id)
    if payload is None:
        await message.answer("Не удалось загрузить вопрос. Попробуй снова /test.")
        await state.clear()
        return

    text, options, _correct = payload
    if cache_state.is_unlimited:
        progress_label = f"#{cache_state.answered + 1} (без лимита)"
    else:
        total = cache_state.target_total or len(cache_state.queue)
        progress_label = f"#{cache_state.answered + 1} из {total}"
    rendered = format_question_text(text, options, cache_state.current_index, len(cache_state.queue))
    rendered = f"<i>{progress_label}</i>\n\n" + rendered
    cache_state.last_question_sent_at = datetime.now(UTC)
    await session_service.cache.save(cache_state)
    bookmarked = await _is_bookmarked(session_service, cache_state.user_id, question_id)
    await message.answer(
        rendered,
        reply_markup=build_answer_keyboard(
            question_id,
            len(options),
            bookmarked=bookmarked,
            hint_available=True,
        ),
    )


async def _finish(
    message: Message,
    session_service: TestSessionService,
    state: FSMContext,
    user_id: int,
    by_user: bool,
) -> None:
    await session_service.flush_session(user_id, mark_finished=True)
    await state.clear()
    suffix = "по твоему запросу" if by_user else "очередь закончилась"
    await message.answer(
        f"Сессия завершена ({suffix}).\n\nПосмотри результат через /stats или запусти ещё.",
        reply_markup=build_finish_keyboard(),
    )


async def _start_for(
    message: Message,
    telegram_user,
    session_service: TestSessionService,
    state: FSMContext,
    category_key: str,
    target_total: int | None,
    is_unlimited: bool,
) -> None:
    if telegram_user is None:
        return
    topics = list_topic_filter(category_key)
    counts_toward_daily = category_key == ALL_CATEGORY_KEY
    result = await session_service.start_session(
        telegram_user,
        topics=topics,
        target_total=target_total,
        is_unlimited=is_unlimited,
        counts_toward_daily=counts_toward_daily,
    )
    if result is None:
        await message.answer(
            "Не нашёл вопросов под выбранные параметры. "
            "Возможно, дневной лимит исчерпан - попробуй другую категорию или режим.",
            reply_markup=build_main_menu(),
        )
        return
    await state.set_state(TestStates.in_session)
    label = display_name(category_key)
    if is_unlimited:
        mode_label = "без лимита"
    elif target_total is not None:
        mode_label = f"{target_total} вопросов"
    else:
        mode_label = f"{len(result.state.queue)} вопросов"
    await message.answer(
        f"Запускаю режим: <b>{escape(label)}</b>, <b>{escape(mode_label)}</b>.\n"
        "Поехали!"
    )
    await _send_current_question(message, telegram_user.id, session_service, state)


@router.message(Command("test"))
async def handle_test_command(
    message: Message,
    session_service: TestSessionService,
    state: FSMContext,
) -> None:
    await message.answer(
        "Выбери категорию вопросов:",
        reply_markup=build_category_keyboard(),
    )


@router.message(Command("algorithms"))
async def handle_algorithms_command(
    message: Message,
    session_service: TestSessionService,
    state: FSMContext,
) -> None:
    await message.answer(
        f"Категория: <b>{escape(display_name(ALGORITHMS_KEY))}</b>\nВыбери режим:",
        reply_markup=build_purpose_keyboard(ALGORITHMS_KEY),
    )


@router.callback_query(F.data == "menu:test")
async def handle_menu_test(
    callback: CallbackQuery,
    session_service: TestSessionService,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await callback.answer()
    await edit_or_send(
        callback,
        "Выбери категорию вопросов:",
        reply_markup=build_category_keyboard(),
    )


@router.callback_query(F.data == "menu:main")
async def handle_menu_main(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await callback.answer()
    await edit_or_send(
        callback,
        "Главное меню. Выбирай, что хочешь сделать:",
        reply_markup=build_main_menu(),
    )


@router.callback_query(F.data.startswith("cat:"))
async def handle_category_pick(
    callback: CallbackQuery,
    session_service: TestSessionService,
    state: FSMContext,
) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return
    parts = callback.data.split(":", 1)
    if len(parts) != 2:
        await callback.answer()
        return
    category_key = parts[1]
    if category_key != ALL_CATEGORY_KEY and category_key not in CATEGORY_BY_KEY:
        await callback.answer("Неизвестная категория", show_alert=True)
        return
    await callback.answer()
    await edit_or_send(
        callback,
        f"Категория: <b>{escape(display_name(category_key))}</b>\n"
        "Выбери режим:",
        reply_markup=build_purpose_keyboard(category_key),
    )


@router.callback_query(F.data.startswith("pur:practice:"))
async def handle_purpose_practice(
    callback: CallbackQuery,
    session_service: TestSessionService,
    state: FSMContext,
) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        await callback.answer()
        return
    category_key = parts[2]
    if category_key != ALL_CATEGORY_KEY and category_key not in CATEGORY_BY_KEY:
        await callback.answer("Неизвестная категория", show_alert=True)
        return
    await callback.answer()
    await edit_or_send(
        callback,
        f"Тренажёр: <b>{escape(display_name(category_key))}</b>\nСколько вопросов решаем?",
        reply_markup=build_mode_keyboard(category_key),
    )


@router.callback_query(F.data.startswith("mode:"))
async def handle_mode_pick(
    callback: CallbackQuery,
    session_service: TestSessionService,
    state: FSMContext,
) -> None:
    if callback.message is None or callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    category_key = parts[1]
    mode_token = parts[2]
    if category_key != ALL_CATEGORY_KEY and category_key not in CATEGORY_BY_KEY:
        await callback.answer("Неизвестная категория", show_alert=True)
        return
    target_total: int | None
    is_unlimited = False
    if mode_token == "inf":
        target_total = None
        is_unlimited = True
    else:
        try:
            target_total = int(mode_token)
        except ValueError:
            await callback.answer()
            return
        valid_values = {value for _label, value in SESSION_MODES if value is not None}
        if target_total not in valid_values:
            await callback.answer()
            return
    await callback.answer()
    await _start_for(
        callback.message,
        callback.from_user,
        session_service,
        state,
        category_key=category_key,
        target_total=target_total,
        is_unlimited=is_unlimited,
    )


@router.callback_query(F.data.startswith("ans:"))
async def handle_answer(
    callback: CallbackQuery,
    session_service: TestSessionService,
    state: FSMContext,
    bot: Bot,
) -> None:
    if callback.from_user is None or callback.message is None or callback.data is None:
        await callback.answer()
        return
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    try:
        question_id = int(parts[1])
        chosen = int(parts[2])
    except ValueError:
        await callback.answer()
        return

    user_id = await _user_id(session_service, callback.from_user.id)
    cache_state = await session_service.cache.load(user_id)
    if cache_state is None:
        await callback.answer("Сессия истекла", show_alert=True)
        await state.clear()
        return
    if cache_state.current_question_id() != question_id:
        await callback.answer("Этот вопрос уже не активен", show_alert=True)
        return

    payload = await session_service.get_question_payload(question_id)
    if payload is None:
        await callback.answer("Вопрос недоступен", show_alert=True)
        return
    _, options, correct_index = payload

    last_sent = cache_state.last_question_sent_at or datetime.now(UTC)
    response_time_ms = max(
        0, int((datetime.now(UTC) - last_sent).total_seconds() * 1000)
    )

    cache_state = await session_service.submit_answer(
        state=cache_state,
        question_id=question_id,
        chosen_index=chosen,
        correct_index=correct_index,
        response_time_ms=response_time_ms,
    )

    is_correct = chosen == correct_index
    feedback_prefix = "Верно" if is_correct else "Неверно"
    chosen_option = options[chosen] if 0 <= chosen < len(options) else ""

    original_text = callback.message.html_text or callback.message.text or ""
    feedback_block = [
        "",
        f"<b>{feedback_prefix}.</b>",
        f"Твой ответ: <b>{chosen + 1}</b>. {render_with_code(chosen_option)}",
        f"Правильный ответ: <b>{correct_index + 1}</b>. {render_with_code(options[correct_index])}",
    ]
    if not is_correct:
        async with session_service.session_factory() as db:
            question_obj = await QuestionRepository(db).get_by_id(question_id)
        explanations = (
            question_obj.option_explanations if question_obj is not None else None
        )
        if explanations and 0 <= chosen < len(explanations):
            wrong_explanation = explanations[chosen]
            if wrong_explanation:
                feedback_block.append("")
                feedback_block.append(
                    f"<i>Почему вариант {chosen + 1} неверен:</i> "
                    f"{escape(clean_text(wrong_explanation))}"
                )
    await callback.answer(feedback_prefix)
    await safe_edit_text(
        callback.message,
        original_text + "\n" + "\n".join(feedback_block),
        reply_markup=build_post_answer_keyboard(
            question_id, chosen if not is_correct else None
        ),
    )

    if not cache_state.is_unlimited and cache_state.remaining() == 0:
        await _finish(callback.message, session_service, state, user_id, by_user=False)
    if len(cache_state.pending) >= 10:
        await session_service.flush_session(user_id, mark_finished=False)
    async with session_service.session_factory() as db:
        new_codes = await evaluate_and_grant(db, user_id)
        await db.commit()
    if new_codes:
        await notify_user_about_codes(bot, callback.from_user.id, new_codes)
    if not cache_state.is_unlimited and cache_state.remaining() == 0:
        return
    await _send_current_question(callback.message, callback.from_user.id, session_service, state)


@router.callback_query(F.data == "test:stop")
async def handle_test_stop(
    callback: CallbackQuery,
    session_service: TestSessionService,
    state: FSMContext,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user_id = await _user_id(session_service, callback.from_user.id)
    await callback.answer()
    await _finish(callback.message, session_service, state, user_id, by_user=True)
