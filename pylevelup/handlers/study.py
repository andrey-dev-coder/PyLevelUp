from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

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
from pylevelup.repositories import UserRepository
from pylevelup.services.study_service import StudyCard, StudyService
from pylevelup.utils.text import clean_text

router = Router(name="pylevelup_study")


def _format_card(card: StudyCard, category_key: str) -> str:
    parts: list[str] = []
    parts.append(f"<i>Изучение - {escape(display_name(category_key))}, карточка #{card.position}</i>")
    parts.append("")
    parts.append(f"<b>{escape(clean_text(card.text))}</b>")
    parts.append("")
    for index, option in enumerate(card.options):
        marker = "✅" if index == card.correct_index else "▫️"
        parts.append(f"{marker} {escape(clean_text(option))}")
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
        await callback.message.answer(
            "Для этой категории пока нет вопросов. Попробуй другую.",
            reply_markup=build_main_menu(),
        )
        return
    await state.clear()
    await state.update_data(study_category=category_key)
    await callback.message.answer(_format_card(card, category_key), reply_markup=build_study_card_keyboard())


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
        await callback.message.answer(
            "Карточки закончились. Возвращайся в меню или выбери другую категорию.",
            reply_markup=build_main_menu(),
        )
        return
    data = await state.get_data()
    category_key = data.get("study_category", ALL_CATEGORY_KEY)
    await callback.answer()
    await callback.message.answer(_format_card(card, category_key), reply_markup=build_study_card_keyboard())


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
    await callback.message.answer(
        "Изучение завершено. Можно перейти к тренажёру или посмотреть статистику.",
        reply_markup=build_main_menu(),
    )
