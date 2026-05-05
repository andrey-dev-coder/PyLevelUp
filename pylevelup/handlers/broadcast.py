from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.config import Settings
from pylevelup.services.broadcast import BroadcastService

router = Router(name="pylevelup_broadcast")


class BroadcastStates(StatesGroup):
    awaiting_text = State()
    awaiting_confirm = State()


def _is_owner(event: Message | CallbackQuery, settings: Settings) -> bool:
    return event.from_user is not None and event.from_user.id == settings.owner_telegram_id


def _confirm_keyboard(recipient_count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Отправить {recipient_count}",
                    callback_data="broadcast:send",
                )
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="broadcast:cancel")],
        ]
    )


def _extract_text(message: Message, args: str | None) -> str | None:
    if args:
        return args.strip() or None
    if message.reply_to_message:
        reply = message.reply_to_message
        if reply.html_text:
            return reply.html_text
        if reply.text:
            return reply.text
        if reply.caption:
            return reply.caption
    return None


@router.message(Command("broadcast"))
async def handle_broadcast(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_owner(message, settings):
        return
    text = _extract_text(message, command.args)
    if text is None:
        await state.set_state(BroadcastStates.awaiting_text)
        await message.answer(
            "Пришли следующим сообщением текст рассылки.\n"
            "Поддерживается HTML-разметка (<b>, <i>, <code>, ссылки).\n"
            "Для отмены - /cancel."
        )
        return
    await _show_preview(message, text, state, session_factory)


@router.message(BroadcastStates.awaiting_text, Command("cancel"))
async def handle_broadcast_cancel(message: Message, state: FSMContext, settings: Settings) -> None:
    if not _is_owner(message, settings):
        return
    await state.clear()
    await message.answer("Рассылка отменена.")


@router.message(BroadcastStates.awaiting_text)
async def handle_broadcast_text(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_owner(message, settings):
        return
    text = message.html_text if message.html_text else (message.text or "")
    text = text.strip()
    if not text:
        await message.answer("Текст пустой. Пришли ещё раз или /cancel.")
        return
    await _show_preview(message, text, state, session_factory)


async def _show_preview(
    message: Message,
    text: str,
    state: FSMContext,
    session_factory: async_sessionmaker,
) -> None:
    service = BroadcastService(session_factory)
    recipient_ids = await service.list_recipient_ids()
    await state.set_state(BroadcastStates.awaiting_confirm)
    await state.update_data(text=text)
    await message.answer(
        f"<b>Превью рассылки</b> (получателей: {len(recipient_ids)})\n"
        f"-----\n{text}\n-----"
    )
    await message.answer(
        "Подтверди отправку:",
        reply_markup=_confirm_keyboard(len(recipient_ids)),
    )


@router.callback_query(F.data == "broadcast:cancel", BroadcastStates.awaiting_confirm)
async def handle_broadcast_cancel_cb(
    call: CallbackQuery,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not _is_owner(call, settings):
        await call.answer()
        return
    await state.clear()
    await call.answer("Отменено")
    if call.message:
        await call.message.edit_text("Рассылка отменена.")


@router.callback_query(F.data == "broadcast:send", BroadcastStates.awaiting_confirm)
async def handle_broadcast_send_cb(
    call: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_owner(call, settings):
        await call.answer()
        return
    data = await state.get_data()
    text: str = data.get("text", "")
    await state.clear()
    await call.answer("Отправляю...")
    if call.message:
        await call.message.edit_text("Рассылка запущена.")
    service = BroadcastService(session_factory)
    result = await service.send_to_all(bot, text)
    await bot.send_message(
        settings.owner_telegram_id,
        (
            "<b>Рассылка завершена</b>\n"
            f"Всего получателей: {result.total}\n"
            f"Доставлено: {result.delivered}\n"
            f"Заблокировали бота: {result.blocked}\n"
            f"Прочих ошибок: {result.failed}"
        ),
    )


@router.message(Command("broadcast_test"))
async def handle_broadcast_test(
    message: Message,
    command: CommandObject,
    bot: Bot,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_owner(message, settings):
        return
    text = _extract_text(message, command.args)
    if text is None:
        await message.answer(
            "Использование: /broadcast_test ТЕКСТ\n"
            "Или ответь этой командой на сообщение, текст которого хочешь рассылать."
        )
        return
    service = BroadcastService(session_factory)
    result = await service.send_to_one(bot, text, settings.owner_telegram_id)
    if result.delivered:
        await message.answer(
            "Тестовое сообщение отправлено только тебе. "
            "Проверь как выглядит и используй /broadcast для всех."
        )
    else:
        await message.answer(
            f"Не удалось отправить тестовое сообщение. "
            f"Заблокировано: {result.blocked}, ошибок: {result.failed}.\n"
            "Скорее всего ошибка в HTML-разметке. "
            "Сырая ошибка по последнему апдейту видна в логах."
        )
