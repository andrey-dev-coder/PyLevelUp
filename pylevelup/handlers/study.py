from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from pylevelup.categories import (
    ALL_CATEGORY_KEY,
    CATEGORY_BY_KEY,
    display_name,
    list_topic_filter,
)
from pylevelup.keyboards import (
    build_main_menu,
    build_study_card_keyboard,
)
from pylevelup.repositories import BookmarkRepository, UserRepository
from pylevelup.services.study_service import StudyCard, StudyService
from pylevelup.utils.edit import safe_edit_text
from pylevelup.utils.text import clean_text

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
    parts.append(f"<b>{escape(clean_text(card.text))}</b>")
    parts.append("")
    for index, option in enumerate(card.options):
        marker = "✅" if index == card.correct_index else "▫️"
        parts.append(f"{marker} {escape(clean_text(option))}")
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
) -> None:
    if callback.message is None or callback.from_user is None or callback.data is None:
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
    topics = list_topic_filter(category_key)
    card = await study_service.start(callback.from_user, topics=topics)
    if card is None:
        await safe_edit_text(
            callback.message,
            "Для этой категории пока нет вопросов. Попробуй другую.",
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
