from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from pylevelup.categories import ALL_CATEGORY_KEY, CATEGORIES, SESSION_MODES


def build_answer_keyboard(question_id: int, options_count: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for option_index in range(options_count):
        builder.button(
            text=f"{option_index + 1}",
            callback_data=f"ans:{question_id}:{option_index}",
        )
    builder.button(text="Завершить тест", callback_data="test:stop")
    builder.adjust(min(options_count, 3), 3, 1)
    return builder.as_markup()


def build_finish_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Запустить ещё", callback_data="menu:test")
    keyboard.button(text="Только алгоритмы", callback_data=f"cat:{'algorithms'}")
    keyboard.button(text="Моя статистика", callback_data="stats:show")
    keyboard.adjust(1)
    return keyboard.as_markup()


def build_main_menu() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Начать тест", callback_data="menu:test")
    keyboard.button(text="Алгоритмы", callback_data="cat:algorithms")
    keyboard.button(text="Работа над ошибками", callback_data="mistakes:start")
    keyboard.button(text="Мой профиль", callback_data="stats:show")
    keyboard.button(text="О проекте", callback_data="info:show")
    keyboard.adjust(1)
    return keyboard.as_markup()


def build_profile_keyboard(has_mistakes: bool) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    if has_mistakes:
        keyboard.button(text="Работа над ошибками", callback_data="mistakes:start")
    keyboard.button(text="Начать тест", callback_data="menu:test")
    keyboard.button(text="В главное меню", callback_data="menu:main")
    keyboard.adjust(1)
    return keyboard.as_markup()


def build_category_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Все темы (микс)", callback_data=f"cat:{ALL_CATEGORY_KEY}")
    for category in CATEGORIES:
        keyboard.button(text=category.title, callback_data=f"cat:{category.key}")
    keyboard.button(text="Назад в меню", callback_data="menu:main")
    keyboard.adjust(1)
    return keyboard.as_markup()


def build_mode_keyboard(category_key: str) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    for label, value in SESSION_MODES:
        token = "inf" if value is None else str(value)
        keyboard.button(text=label, callback_data=f"mode:{category_key}:{token}")
    keyboard.button(text="Назад", callback_data=f"cat:{category_key}")
    keyboard.adjust(1)
    return keyboard.as_markup()


def build_purpose_keyboard(category_key: str) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Изучение (карточки с ответами)", callback_data=f"pur:study:{category_key}")
    keyboard.button(text="Тренажёр (тест)", callback_data=f"pur:practice:{category_key}")
    keyboard.button(text="Назад к категориям", callback_data="menu:test")
    keyboard.adjust(1)
    return keyboard.as_markup()


def build_study_card_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Дальше", callback_data="study:next")
    keyboard.button(text="Завершить изучение", callback_data="study:stop")
    keyboard.adjust(1)
    return keyboard.as_markup()


__all__ = [
    "InlineKeyboardButton",
    "InlineKeyboardMarkup",
    "build_answer_keyboard",
    "build_category_keyboard",
    "build_finish_keyboard",
    "build_main_menu",
    "build_mode_keyboard",
    "build_profile_keyboard",
    "build_purpose_keyboard",
    "build_study_card_keyboard",
]
