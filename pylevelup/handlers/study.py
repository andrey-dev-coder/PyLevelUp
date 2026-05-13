from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.categories import (
    ALL_CATEGORY_KEY,
    all_category_keys,
    display_name,
    list_topic_filter,
)
from pylevelup.db.models import OpenQuestion
from pylevelup.keyboards import (
    build_main_menu,
    build_study_card_keyboard,
)
from pylevelup.repositories import BookmarkRepository, OpenQuestionRepository, UserRepository
from pylevelup.services.study_service import StudyCard, StudyService
from pylevelup.utils.edit import safe_edit_text
from pylevelup.utils.text import clean_text, render_with_code

router = Router(name="pylevelup_study")


MISTAKES_KEY = "__mistakes__"


def _format_card(card: StudyCard, category_key: str) -> str:
    parts: list[str] = []
    if category_key == MISTAKES_KEY:
        header = f"<i>Работа над ошибками, карточка #{card.position} из {card.total}</i>"
    else:
        header = f"<i>Изучение - {escape(display_name(category_key))}, карточка #{card.position}</i>"
    parts.append(header)
    parts.append("")
    parts.append(f"<b>{render_with_code(card.text)}</b>")
    parts.append("")
    for index, option in enumerate(card.options):
        marker = "✅" if index == card.correct_index else "▫️"
        parts.append(f"{marker} {render_with_code(option)}")
    option_explanations = getattr(card, "option_explanations", None)
    if option_explanations:
        parts.append("")
        parts.append("<b>По вариантам</b>")
        for index, explanation in enumerate(option_explanations):
            if not explanation or index == card.correct_index:
                continue
            parts.append(
                f"{index + 1}. {escape(clean_text(explanation))}"
            )
    if card.explanation:
        parts.append("")
        parts.append("<b>Пояснение</b>")
        parts.append(escape(clean_text(card.explanation)))
    return "\n".join(parts)


async def _user_id(study_service: StudyService, telegram_id: int) -> int | None:
    async with study_service.session_factory() as db:
        user = await UserRepository(db).get_by_telegram_id(telegram_id)
        if user is None:
            return None
        return user.id


async def _is_bookmarked(study_service: StudyService, user_id: int, question_id: int) -> bool:
    async with study_service.session_factory() as db:
        return await BookmarkRepository(db).is_bookmarked(user_id, question_id)


async def _send_card(
    target,
    study_service: StudyService,
    telegram_id: int,
    card: StudyCard,
    category_key: str,
    edit: bool = False,
) -> None:
    user_id = await _user_id(study_service, telegram_id)
    bookmarked = False
    if user_id is not None:
        bookmarked = await _is_bookmarked(study_service, user_id, card.question_id)
    text = _format_card(card, category_key)
    markup = build_study_card_keyboard(
        question_id=card.question_id,
        bookmarked=bookmarked,
    )
    if edit:
        await safe_edit_text(target, text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("pur:study:"))
async def handle_purpose_study(
    callback: CallbackQuery,
    study_service: StudyService,
    state: FSMContext,
    session_factory: async_sessionmaker,
) -> None:
    if callback.message is None or callback.from_user is None or callback.data is None:
        await callback.answer()
        return
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        await callback.answer()
        return
    category_key = parts[2]
    if category_key != ALL_CATEGORY_KEY and category_key not in all_category_keys():
        await callback.answer("Неизвестная категория", show_alert=True)
        return
    await callback.answer()
    topics = list_topic_filter(category_key)
    card = await study_service.start(callback.from_user, topics=topics)
    if card is None:
        topic_for_theory = category_key if category_key != ALL_CATEGORY_KEY else None
        async with session_factory() as db:
            theory_card = await OpenQuestionRepository(db).random_active(topic=topic_for_theory)
        if theory_card is not None:
            await state.clear()
            await state.update_data(theory_category=category_key)
            await safe_edit_text(
                callback.message,
                _format_theory_question(theory_card, category_key),
                reply_markup=_theory_question_keyboard(theory_card.id),
            )
            return
        await safe_edit_text(
            callback.message,
            "Для этой категории пока нет ни тестовых вопросов, ни теории.",
            reply_markup=build_main_menu(),
        )
        return
    await state.clear()
    await state.update_data(study_category=category_key)
    await _send_card(
        callback.message,
        study_service,
        callback.from_user.id,
        card,
        category_key,
        edit=True,
    )


def _format_theory_question(question: OpenQuestion, category_key: str) -> str:
    header_name = display_name(category_key) if category_key != ALL_CATEGORY_KEY else display_name(question.topic)
    return (
        f"<i>Теория - {escape(header_name)}</i>\n\n"
        f"<b>{render_with_code(question.text)}</b>\n\n"
        "Сформулируй ответ для себя, затем нажми <b>Показать ответ</b>."
    )


def _format_theory_answer(question: OpenQuestion, category_key: str) -> str:
    header_name = display_name(category_key) if category_key != ALL_CATEGORY_KEY else display_name(question.topic)
    parts: list[str] = [
        f"<i>Теория - {escape(header_name)}</i>",
        "",
        f"<b>{render_with_code(question.text)}</b>",
        "",
        "<b>Эталонный ответ</b>",
        render_with_code(question.ideal_answer),
    ]
    if question.checklist:
        parts.append("")
        parts.append("<b>Чек-лист пунктов</b>")
        for item in question.checklist:
            parts.append(f"- {render_with_code(item)}")
    return "\n".join(parts)


def _theory_question_keyboard(question_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Показать ответ", callback_data=f"th:show:{question_id}")],
            [
                InlineKeyboardButton(text="Следующая →", callback_data="th:next"),
                InlineKeyboardButton(text="Завершить", callback_data="th:stop"),
            ],
        ]
    )


def _theory_answer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Следующая карточка →", callback_data="th:next")],
            [InlineKeyboardButton(text="Завершить", callback_data="th:stop")],
        ]
    )


@router.callback_query(F.data.startswith("th:show:"))
async def handle_theory_show_answer(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker,
) -> None:
    if callback.message is None or callback.data is None:
        await callback.answer()
        return
    try:
        question_id = int(callback.data.split(":", 2)[2])
    except (ValueError, IndexError):
        await callback.answer()
        return
    async with session_factory() as db:
        question = await OpenQuestionRepository(db).get(question_id)
    if question is None:
        await callback.answer("Карточка недоступна", show_alert=True)
        return
    data = await state.get_data()
    category_key = data.get("theory_category", ALL_CATEGORY_KEY)
    await callback.answer()
    await safe_edit_text(
        callback.message,
        _format_theory_answer(question, category_key),
        reply_markup=_theory_answer_keyboard(),
    )


@router.callback_query(F.data == "th:next")
async def handle_theory_next(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    data = await state.get_data()
    category_key = data.get("theory_category", ALL_CATEGORY_KEY)
    topic = category_key if category_key != ALL_CATEGORY_KEY else None
    async with session_factory() as db:
        question = await OpenQuestionRepository(db).random_active(topic=topic)
    await callback.answer()
    if question is None:
        await safe_edit_text(
            callback.message,
            "Карточек больше нет.",
            reply_markup=build_main_menu(),
        )
        return
    await safe_edit_text(
        callback.message,
        _format_theory_question(question, category_key),
        reply_markup=_theory_question_keyboard(question.id),
    )


@router.callback_query(F.data == "th:stop")
async def handle_theory_stop(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await state.clear()
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "Изучение теории завершено.",
        reply_markup=build_main_menu(),
    )


async def _start_mistakes_session(
    target: Message,
    telegram_user,
    study_service: StudyService,
    state: FSMContext,
) -> None:
    card = await study_service.start_mistakes(telegram_user)
    if card is None:
        await target.answer(
            "Ошибок пока нет - либо ты ещё не проходил тренажёр, либо отвечаешь идеально. "
            "Запусти 'Начать тест' и потренируйся.",
            reply_markup=build_main_menu(),
        )
        return
    await state.clear()
    await state.update_data(study_category=MISTAKES_KEY)
    await _send_card(target, study_service, telegram_user.id, card, MISTAKES_KEY)


@router.callback_query(F.data == "mistakes:start")
async def handle_mistakes_start(
    callback: CallbackQuery,
    study_service: StudyService,
    state: FSMContext,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    await callback.answer()
    await _start_mistakes_session(callback.message, callback.from_user, study_service, state)


@router.message(Command("mistakes"))
async def handle_mistakes_command(
    message: Message,
    study_service: StudyService,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        return
    await _start_mistakes_session(message, message.from_user, study_service, state)


@router.callback_query(F.data == "study:next")
async def handle_study_next(
    callback: CallbackQuery,
    study_service: StudyService,
    state: FSMContext,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    user_id = await _user_id(study_service, callback.from_user.id)
    if user_id is None:
        await callback.answer()
        return
    card = await study_service.next_card(user_id)
    if card is None:
        await callback.answer()
        await safe_edit_text(
            callback.message,
            "Карточки закончились. Возвращайся в меню или выбери другую категорию.",
            reply_markup=build_main_menu(),
        )
        return
    data = await state.get_data()
    category_key = data.get("study_category", ALL_CATEGORY_KEY)
    await callback.answer()
    await _send_card(
        callback.message,
        study_service,
        callback.from_user.id,
        card,
        category_key,
        edit=True,
    )


@router.callback_query(F.data == "study:stop")
async def handle_study_stop(
    callback: CallbackQuery,
    study_service: StudyService,
    state: FSMContext,
) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    user_id = await _user_id(study_service, callback.from_user.id)
    if user_id is not None:
        await study_service.clear(user_id)
    await state.clear()
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "Изучение завершено. Можно перейти к тренажёру или посмотреть статистику.",
        reply_markup=build_main_menu(),
    )
