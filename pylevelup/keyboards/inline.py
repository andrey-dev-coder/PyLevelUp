from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


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
    keyboard.button(text="Запустить ещё", callback_data="test:start")
    keyboard.button(text="Моя статистика", callback_data="stats:show")
    keyboard.adjust(1)
    return keyboard.as_markup()


def build_main_menu() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Начать тест", callback_data="test:start")
    keyboard.button(text="Моя статистика", callback_data="stats:show")
    keyboard.button(text="О проекте", callback_data="info:show")
    keyboard.adjust(1)
    return keyboard.as_markup()


__all__ = [
    "InlineKeyboardButton",
    "InlineKeyboardMarkup",
    "build_answer_keyboard",
    "build_finish_keyboard",
    "build_main_menu",
]
