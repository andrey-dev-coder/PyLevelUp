from datetime import UTC, datetime
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from pylevelup.keyboards import build_answer_keyboard, build_finish_keyboard
from pylevelup.services.test_session_service import TestSessionService
from pylevelup.states import TestStates
from pylevelup.utils.text import clean_text, format_question_text

router = Router(name="pylevelup_test")


async def _send_current_question(
    message: Message,
    telegram_id: int,
    session_service: TestSessionService,
    state: FSMContext,
) -> None:
    cache_state = await session_service.cache.load(await _user_id(session_service, telegram_id))
    if cache_state is None:
        await message.answer("Сессия не найдена. Запусти заново командой /test.")
        await state.clear()
        return

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
    rendered = format_question_text(text, options, cache_state.current_index, len(cache_state.queue))
    cache_state.last_question_sent_at = datetime.now(UTC)
    await session_service.cache.save(cache_state)
    await message.answer(
        rendered,
        reply_markup=build_answer_keyboard(question_id, len(options)),
    )


async def _user_id(session_service: TestSessionService, telegram_id: int) -> int:
    async with session_service.session_factory() as db:
        from pylevelup.repositories import UserRepository

        user = await UserRepository(db).get_by_telegram_id(telegram_id)
        if user is None:
            raise RuntimeError("user not found")
        return user.id


async def _finish(
    message: Message,
    session_service: TestSessionService,
    state: FSMContext,
    user_id: int,
    by_user: bool,
) -> None:
    await session_service.flush_session(user_id, mark_finished=True)
    await state.clear()
    suffix = "по твоему запросу" if by_user else "лимит исчерпан"
    await message.answer(
        f"Сессия завершена ({suffix}).\n\nПосмотри результат: /stats",
        reply_markup=build_finish_keyboard(),
    )


async def _start_for(
    message: Message,
    telegram_user,
    session_service: TestSessionService,
    state: FSMContext,
) -> None:
    if telegram_user is None:
        return
    result = await session_service.start_session(telegram_user)
    if result is None:
        await message.answer(
            "На сегодня лимит из 50 вопросов уже исчерпан или нет доступных вопросов. "
            "Возвращайся завтра или загляни в /stats."
        )
        return
    await state.set_state(TestStates.in_session)
    await message.answer(
        f"Сессия запущена. В очереди {len(result.state.queue)} вопросов. Поехали!"
    )
    await _send_current_question(message, telegram_user.id, session_service, state)


@router.message(Command("test"))
async def handle_test_command(
    message: Message,
    session_service: TestSessionService,
    state: FSMContext,
) -> None:
    await _start_for(message, message.from_user, session_service, state)


@router.callback_query(F.data == "test:start")
async def handle_test_start_callback(
    callback: CallbackQuery,
    session_service: TestSessionService,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await callback.answer()
    await _start_for(callback.message, callback.from_user, session_service, state)


@router.callback_query(F.data.startswith("ans:"))
async def handle_answer(
    callback: CallbackQuery,
    session_service: TestSessionService,
    state: FSMContext,
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
    correct_option_text = clean_text(options[correct_index])
    feedback_prefix = "Верно" if is_correct else "Неверно"
    feedback = (
        f"<b>{feedback_prefix}.</b>\nПравильный ответ: <b>{correct_index + 1}</b>. "
        f"{escape(correct_option_text)}"
    )
    await callback.message.answer(feedback)
    await callback.answer()

    if cache_state.remaining() == 0:
        await _finish(callback.message, session_service, state, user_id, by_user=False)
        return
    if len(cache_state.pending) >= 10:
        await session_service.flush_session(user_id, mark_finished=False)
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
