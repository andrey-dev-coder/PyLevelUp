from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

router = Router(name="pylevelup_info")

INFO_TEXT = (
    "<b>PyLevelUp</b>\n\n"
    "Telegram-бот для подготовки к техническим собеседованиям по Python.\n\n"
    "<b>Что внутри:</b>\n"
    "1. Алгоритм интервального повторения (адаптация SuperMemo-2). Бот сам решает, "
    "какие вопросы показать сегодня, чтобы максимизировать запоминание.\n"
    "2. Ежедневная сессия до 50 вопросов с inline-кнопками.\n"
    "3. Промежуточная статистика по сессии хранится в Redis. В PostgreSQL "
    "сбрасывается одной пачкой по завершении сессии: меньше транзакций, выше "
    "устойчивость к нагрузке.\n"
    "4. Глобальный рейтинг считается через оконные функции SQL и периодически "
    "пересчитывается в фоновой задаче Celery.\n"
    "5. Ежедневные напоминания делаются через Celery Beat.\n\n"
    "<b>Команды:</b>\n"
    "/test - запустить ежедневную сессию\n"
    "/stats - персональная статистика\n"
    "/info - это сообщение\n\n"
    "Бот разработан в качестве пет-проекта. Разработчик: Муратов Андрей. "
    "Если вы столкнулись с ошибкой или у вас есть предложения по улучшению, "
    "пожалуйста, напишите в Telegram: @m203ac."
)


@router.message(Command("info"))
async def handle_info(message: Message) -> None:
    await message.answer(INFO_TEXT, disable_web_page_preview=True)


@router.callback_query(F.data == "info:show")
async def handle_info_callback(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await callback.message.answer(INFO_TEXT, disable_web_page_preview=True)
    await callback.answer()
