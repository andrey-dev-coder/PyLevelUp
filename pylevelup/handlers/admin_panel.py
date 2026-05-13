from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.categories import CATEGORIES, custom_categories, display_name
from pylevelup.config import Settings
from pylevelup.repositories import (
    ACCESS_CODE_KEY,
    AccessCodeRepository,
    SettingsRepository,
    TopicAccessRepository,
    UserRepository,
)
from pylevelup.utils.edit import safe_edit_text

router = Router(name="pylevelup_admin_panel")

PAGE_SIZE = 10


class AccessCodeStates(StatesGroup):
    entering_code = State()
    entering_label = State()
    selecting_topics = State()


def _owner(user_id: int | None, settings: Settings) -> bool:
    return user_id is not None and user_id == settings.owner_telegram_id


def _all_topic_keys() -> list[str]:
    return [c.key for c in CATEGORIES] + [c.key for c in custom_categories()]


def _root_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="ap:users:0")],
            [InlineKeyboardButton(text="🔑 Коды доступа", callback_data="ap:codes")],
            [InlineKeyboardButton(text="📚 Категории", callback_data="ap:cats")],
            [InlineKeyboardButton(text="📥 Импорт вопросов", callback_data="ap:import")],
            [InlineKeyboardButton(text="🚩 Жалобы", callback_data="ap:reports")],
            [InlineKeyboardButton(text="📊 Дашборд", callback_data="ap:dash")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="ap:broadcast")],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="ap:close")],
        ]
    )


@router.message(Command("panel"))
async def handle_panel_cmd(
    message: Message,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    await state.clear()
    await message.answer(
        "<b>Панель управления</b>\nВыбери раздел:",
        reply_markup=_root_menu(),
    )


@router.callback_query(F.data == "ap:root")
async def handle_back_to_root(
    call: CallbackQuery,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    await state.clear()
    await call.answer()
    await safe_edit_text(
        call.message,
        "<b>Панель управления</b>\nВыбери раздел:",
        reply_markup=_root_menu(),
    )


@router.callback_query(F.data == "ap:close")
async def handle_close(
    call: CallbackQuery,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    await state.clear()
    await call.answer()
    await safe_edit_text(call.message, "Панель закрыта.")


@router.callback_query(F.data.startswith("ap:users:"))
async def handle_users_list(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    page = int(call.data.split(":")[2])
    offset = page * PAGE_SIZE
    async with session_factory() as db:
        repo = UserRepository(db)
        users = await repo.list_page(offset=offset, limit=PAGE_SIZE)
        total = await repo.total_count()
    await call.answer()
    rows: list[list[InlineKeyboardButton]] = []
    for u in users:
        name = u.username or u.first_name or "no name"
        flags = []
        if u.is_banned:
            flags.append("BAN")
        elif u.is_authorized:
            flags.append("OK")
        else:
            flags.append("new")
        label = f"{name} ({', '.join(flags)})"
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"ap:ucard:{u.id}")]
        )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="<< Назад", callback_data=f"ap:users:{page - 1}"))
    if offset + PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="Вперёд >>", callback_data=f"ap:users:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="<< Панель", callback_data="ap:root")])
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    text = (
        f"<b>Пользователи</b>\n"
        f"Всего: {total} | стр. {page + 1}/{total_pages}\n"
        f"Тыкни на юзера для управления."
    )
    await safe_edit_text(call.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("ap:ucard:"))
async def handle_user_card(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    try:
        user_id = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)
        if user is None:
            await call.answer("Пользователь не найден")
            return
        ta_repo = TopicAccessRepository(db)
        allowed = await ta_repo.list_topics(user.id)
    await call.answer()
    name = escape(user.username or user.first_name or "без имени")
    status = "забанен" if user.is_banned else ("авторизован" if user.is_authorized else "не авторизован")
    access_info = f"{len(allowed)} тем" if allowed else "все (по умолчанию)"
    text = (
        f"<b>Пользователь</b>\n"
        f"ID: <code>{user.telegram_id}</code>\n"
        f"Имя: {name}\n"
        f"Статус: {status}\n"
        f"Доступ: {access_info}\n"
        f"Стрик: {user.current_streak} | макс {user.max_streak}\n"
        f"Ответов: {user.total_answered} | точных: {user.total_correct}\n"
    )
    ban_btn_text = "Разбанить" if user.is_banned else "Забанить"
    ban_action = "unban" if user.is_banned else "ban"
    rows = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data=f"ap:ustats:{user.id}")],
        [InlineKeyboardButton(text="📂 Темы доступа", callback_data=f"ap:utop:{user.id}")],
        [InlineKeyboardButton(text=f"{'🔓' if user.is_banned else '🔒'} {ban_btn_text}", callback_data=f"ap:u{ban_action}:{user.id}")],
        [InlineKeyboardButton(text="<< Пользователи", callback_data="ap:users:0")],
    ]
    await safe_edit_text(call.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("ap:ustats:"))
async def handle_user_stats_panel(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    try:
        user_id = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)
        if user is None:
            await call.answer("Пользователь не найден")
            return
        from pylevelup.handlers.user_admin import _build_user_report

        report = await _build_user_report(db, user)
    await call.answer()
    rows = [
        [InlineKeyboardButton(text="<< Назад", callback_data=f"ap:ucard:{user_id}")],
    ]
    await safe_edit_text(call.message, report, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("ap:uban:"))
async def handle_user_ban_panel(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    try:
        user_id = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)
        if user is None:
            await call.answer("Не найден")
            return
        if user.telegram_id == settings.owner_telegram_id:
            await call.answer("Нельзя забанить самого себя", show_alert=True)
            return
        await user_repo.set_banned(user.telegram_id, banned=True)
        await db.commit()
    await call.answer("Забанен")
    await _refresh_user_card(call, session_factory, user_id)


@router.callback_query(F.data.startswith("ap:uunban:"))
async def handle_user_unban_panel(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    try:
        user_id = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)
        if user is None:
            await call.answer("Не найден")
            return
        await user_repo.set_banned(user.telegram_id, banned=False)
        await db.commit()
    await call.answer("Разбанен")
    await _refresh_user_card(call, session_factory, user_id)


async def _refresh_user_card(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    user_id: int,
) -> None:
    async with session_factory() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)
        if user is None:
            return
        ta_repo = TopicAccessRepository(db)
        allowed = await ta_repo.list_topics(user.id)
    name = escape(user.username or user.first_name or "без имени")
    status = "забанен" if user.is_banned else ("авторизован" if user.is_authorized else "не авторизован")
    access_info = f"{len(allowed)} тем" if allowed else "все (по умолчанию)"
    text = (
        f"<b>Пользователь</b>\n"
        f"ID: <code>{user.telegram_id}</code>\n"
        f"Имя: {name}\n"
        f"Статус: {status}\n"
        f"Доступ: {access_info}\n"
        f"Стрик: {user.current_streak} | макс {user.max_streak}\n"
        f"Ответов: {user.total_answered} | точных: {user.total_correct}\n"
    )
    ban_btn_text = "Разбанить" if user.is_banned else "Забанить"
    ban_action = "unban" if user.is_banned else "ban"
    rows = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data=f"ap:ustats:{user.id}")],
        [InlineKeyboardButton(text="📂 Темы доступа", callback_data=f"ap:utop:{user.id}")],
        [InlineKeyboardButton(
            text=f"{'🔓' if user.is_banned else '🔒'} {ban_btn_text}",
            callback_data=f"ap:u{ban_action}:{user.id}",
        )],
        [InlineKeyboardButton(text="<< Пользователи", callback_data="ap:users:0")],
    ]
    await safe_edit_text(call.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("ap:utop:"))
async def handle_user_topics_panel(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    try:
        user_id = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)
        if user is None:
            await call.answer("Не найден")
            return
        ta_repo = TopicAccessRepository(db)
        allowed = await ta_repo.list_topics(user.id)
    allowed_set = set(allowed)
    await call.answer()
    name = escape(user.username or user.first_name or "без имени")
    access_info = f"{len(allowed)} тем" if allowed else "все (по умолчанию)"
    text = (
        f"<b>Темы доступа</b>\n"
        f"Юзер: {name} (<code>{user.telegram_id}</code>)\n"
        f"Доступ: {access_info}\n\n"
        "Отметь темы, которые открыть. Пустой список = все."
    )
    await safe_edit_text(
        call.message,
        text,
        reply_markup=_user_topics_kb(user.id, allowed_set),
    )


def _user_topics_kb(user_id: int, allowed: set[str]) -> InlineKeyboardMarkup:
    is_default = len(allowed) == 0
    rows: list[list[InlineKeyboardButton]] = []
    for cat in CATEGORIES:
        checked = is_default or cat.key in allowed
        prefix = "☑" if checked else "▫️"
        rows.append(
            [InlineKeyboardButton(
                text=f"{prefix} {cat.short}",
                callback_data=f"ap:utopt:{user_id}:{cat.key}",
            )]
        )
    for cat in custom_categories():
        checked = is_default or cat.key in allowed
        prefix = "☑" if checked else "▫️"
        rows.append(
            [InlineKeyboardButton(
                text=f"{prefix} {cat.short} (своя)",
                callback_data=f"ap:utopt:{user_id}:{cat.key}",
            )]
        )
    rows.append(
        [InlineKeyboardButton(
            text="Все темы (сброс к дефолту)",
            callback_data=f"ap:utopreset:{user_id}",
        )]
    )
    rows.append(
        [InlineKeyboardButton(text="<< Назад", callback_data=f"ap:ucard:{user_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("ap:utopt:"))
async def handle_toggle_topic_panel(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    parts = call.data.split(":", 3)
    if len(parts) != 4:
        await call.answer()
        return
    try:
        user_id = int(parts[2])
    except ValueError:
        await call.answer()
        return
    topic_key = parts[3]
    known = set(_all_topic_keys())
    if topic_key not in known:
        await call.answer("Неизвестная категория", show_alert=True)
        return
    async with session_factory() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)
        if user is None:
            await call.answer("Не найден")
            return
        ta_repo = TopicAccessRepository(db)
        current = await ta_repo.list_topics(user.id)
        if not current:
            new_allowed = [k for k in known if k != topic_key]
            for k in new_allowed:
                await ta_repo.grant(user.id, k)
        elif topic_key in current:
            await ta_repo.revoke(user.id, topic_key)
            new_allowed = [k for k in current if k != topic_key]
        else:
            await ta_repo.grant(user.id, topic_key)
            new_allowed = current + [topic_key]
        if set(new_allowed) == known:
            await ta_repo.clear(user.id)
            new_allowed = []
        await db.commit()
    await call.answer()
    name = escape(user.username or user.first_name or "без имени")
    access_info = f"{len(new_allowed)} тем" if new_allowed else "все (по умолчанию)"
    text = (
        f"<b>Темы доступа</b>\n"
        f"Юзер: {name} (<code>{user.telegram_id}</code>)\n"
        f"Доступ: {access_info}\n\n"
        "Отметь темы, которые открыть. Пустой список = все."
    )
    await safe_edit_text(
        call.message,
        text,
        reply_markup=_user_topics_kb(user.id, set(new_allowed)),
    )


@router.callback_query(F.data.startswith("ap:utopreset:"))
async def handle_reset_topics_panel(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    try:
        user_id = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        ta_repo = TopicAccessRepository(db)
        await ta_repo.clear(user_id)
        await db.commit()
    await call.answer("Сброшено")
    async with session_factory() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)
    if user is None:
        return
    name = escape(user.username or user.first_name or "без имени")
    text = (
        f"<b>Темы доступа</b>\n"
        f"Юзер: {name} (<code>{user.telegram_id}</code>)\n"
        f"Доступ: все (по умолчанию)\n\n"
        "Отметь темы, которые открыть. Пустой список = все."
    )
    await safe_edit_text(call.message, text, reply_markup=_user_topics_kb(user_id, set()))


@router.callback_query(F.data == "ap:codes")
async def handle_codes_list(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.message is None:
        await call.answer()
        return
    await call.answer()
    async with session_factory() as db:
        settings_repo = SettingsRepository(db)
        global_code = await settings_repo.get_or_create(ACCESS_CODE_KEY, settings.default_access_code)
        await db.commit()
        ac_repo = AccessCodeRepository(db)
        codes = await ac_repo.list_all()
    rows: list[list[InlineKeyboardButton]] = []
    lines = [
        "<b>Коды доступа</b>\n",
        f"Глобальный код (все темы): <code>{escape(global_code)}</code>\n",
    ]
    if codes:
        lines.append("<b>Коды с ограничением тем:</b>")
        for ac in codes:
            topics_label = ", ".join(display_name(t) for t in (ac.allowed_topics or []))
            if len(topics_label) > 120:
                topics_label = f"{len(ac.allowed_topics)} тем"
            lines.append(f"- <code>{escape(ac.code)}</code> ({escape(ac.label)}): {topics_label}")
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"Изменить: {ac.label}",
                        callback_data=f"ap:cedit:{ac.code}",
                    ),
                    InlineKeyboardButton(
                        text="Удалить",
                        callback_data=f"ap:cdel:{ac.code}",
                    ),
                ]
            )
    else:
        lines.append("Пользовательских кодов пока нет.")
    rows.append(
        [InlineKeyboardButton(text="➕ Создать код", callback_data="ap:cnew")]
    )
    rows.append(
        [InlineKeyboardButton(text="<< Панель", callback_data="ap:root")]
    )
    await safe_edit_text(
        call.message,
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data == "ap:cnew")
async def handle_new_code_start(
    call: CallbackQuery,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.message is None:
        await call.answer()
        return
    await call.answer()
    await state.set_state(AccessCodeStates.entering_code)
    await safe_edit_text(
        call.message,
        "<b>Создание кода доступа</b>\n\n"
        "Введи кодовое слово (3-128 символов).\n"
        "Пользователи будут вводить его для авторизации.\n\n"
        "Отправь /cancel для отмены.",
    )


@router.message(AccessCodeStates.entering_code)
async def handle_new_code_text(
    message: Message,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=_root_menu())
        return
    code = (message.text or "").strip()
    if len(code) < 3 or len(code) > 128:
        await message.answer("Код от 3 до 128 символов. Попробуй ещё раз.")
        return
    await state.update_data(new_code=code)
    await state.set_state(AccessCodeStates.entering_label)
    await message.answer(
        f"Код: <code>{escape(code)}</code>\n\n"
        "Теперь введи читаемое название (label).\n"
        "Например: 'Backend', 'Junior Python', 'Data Science'.\n\n"
        "/cancel для отмены.",
    )


@router.message(AccessCodeStates.entering_label)
async def handle_new_code_label(
    message: Message,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=_root_menu())
        return
    label = (message.text or "").strip()
    if len(label) < 1 or len(label) > 128:
        await message.answer("Label от 1 до 128 символов. Попробуй ещё раз.")
        return
    await state.update_data(new_label=label)
    await state.set_state(AccessCodeStates.selecting_topics)
    await state.update_data(new_topics=[])
    data = await state.get_data()
    await message.answer(
        f"Код: <code>{escape(data['new_code'])}</code>\n"
        f"Название: {escape(label)}\n\n"
        "Теперь отметь темы, которые откроются пользователям с этим кодом:",
        reply_markup=_code_topics_kb([], editing=False),
    )


def _code_topics_kb(selected: list[str], editing: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for cat in CATEGORIES:
        checked = cat.key in selected
        prefix = "☑" if checked else "▫️"
        rows.append(
            [InlineKeyboardButton(
                text=f"{prefix} {cat.short}",
                callback_data=f"ap:ctog:{cat.key}",
            )]
        )
    for cat in custom_categories():
        checked = cat.key in selected
        prefix = "☑" if checked else "▫️"
        rows.append(
            [InlineKeyboardButton(
                text=f"{prefix} {cat.short} (своя)",
                callback_data=f"ap:ctog:{cat.key}",
            )]
        )
    rows.append(
        [InlineKeyboardButton(text="Выбрать все", callback_data="ap:ctogall")]
    )
    if editing:
        rows.append(
            [InlineKeyboardButton(
                text=f"Сохранить ({len(selected)} тем)",
                callback_data="ap:csave_edit",
            )]
        )
    else:
        rows.append(
            [InlineKeyboardButton(
                text=f"Сохранить ({len(selected)} тем)",
                callback_data="ap:csave",
            )]
        )
    rows.append(
        [InlineKeyboardButton(text="Отмена", callback_data="ap:codes")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("ap:ctog:"), AccessCodeStates.selecting_topics)
async def handle_toggle_topic_for_code(
    call: CallbackQuery,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    topic_key = call.data.split(":", 2)[2]
    known = set(_all_topic_keys())
    if topic_key not in known:
        await call.answer()
        return
    data = await state.get_data()
    selected: list[str] = list(data.get("new_topics") or [])
    if topic_key in selected:
        selected.remove(topic_key)
    else:
        selected.append(topic_key)
    await state.update_data(new_topics=selected)
    await call.answer()
    editing = data.get("editing_code") is not None
    try:
        await call.message.edit_reply_markup(reply_markup=_code_topics_kb(selected, editing=editing))
    except Exception:
        pass


@router.callback_query(F.data == "ap:ctogall", AccessCodeStates.selecting_topics)
async def handle_toggle_all_for_code(
    call: CallbackQuery,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.message is None:
        await call.answer()
        return
    data = await state.get_data()
    selected: list[str] = list(data.get("new_topics") or [])
    all_keys = _all_topic_keys()
    if set(selected) == set(all_keys):
        selected = []
    else:
        selected = list(all_keys)
    await state.update_data(new_topics=selected)
    await call.answer()
    editing = data.get("editing_code") is not None
    try:
        await call.message.edit_reply_markup(reply_markup=_code_topics_kb(selected, editing=editing))
    except Exception:
        pass


@router.callback_query(F.data == "ap:csave", AccessCodeStates.selecting_topics)
async def handle_save_new_code(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.message is None:
        await call.answer()
        return
    data = await state.get_data()
    code = data.get("new_code", "")
    label = data.get("new_label", "")
    selected: list[str] = list(data.get("new_topics") or [])
    if not selected:
        await call.answer("Выбери хотя бы одну тему", show_alert=True)
        return
    async with session_factory() as db:
        ac_repo = AccessCodeRepository(db)
        await ac_repo.upsert(code, label, selected)
        await db.commit()
    await state.clear()
    await call.answer("Код создан")
    topics_label = ", ".join(display_name(t) for t in selected)
    if len(topics_label) > 200:
        topics_label = f"{len(selected)} тем"
    await safe_edit_text(
        call.message,
        f"Код <code>{escape(code)}</code> ({escape(label)}) создан.\n"
        f"Темы: {topics_label}\n\n"
        "Теперь пользователь может ввести этот код вместо глобального, "
        "и ему откроются только выбранные темы.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="<< Коды доступа", callback_data="ap:codes")],
                [InlineKeyboardButton(text="<< Панель", callback_data="ap:root")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("ap:cedit:"))
async def handle_edit_code(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    code = call.data.split(":", 2)[2]
    async with session_factory() as db:
        ac_repo = AccessCodeRepository(db)
        ac = await ac_repo.get(code)
    if ac is None:
        await call.answer("Код не найден", show_alert=True)
        return
    await call.answer()
    await state.set_state(AccessCodeStates.selecting_topics)
    await state.update_data(
        editing_code=code,
        new_code=code,
        new_label=ac.label,
        new_topics=list(ac.allowed_topics or []),
    )
    await safe_edit_text(
        call.message,
        f"<b>Изменение кода</b>\n"
        f"Код: <code>{escape(code)}</code> ({escape(ac.label)})\n\n"
        "Отметь темы заново и нажми 'Сохранить':",
        reply_markup=_code_topics_kb(list(ac.allowed_topics or []), editing=True),
    )


@router.callback_query(F.data == "ap:csave_edit", AccessCodeStates.selecting_topics)
async def handle_save_edit_code(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.message is None:
        await call.answer()
        return
    data = await state.get_data()
    code = data.get("editing_code") or data.get("new_code", "")
    label = data.get("new_label", "")
    selected: list[str] = list(data.get("new_topics") or [])
    if not selected:
        await call.answer("Выбери хотя бы одну тему", show_alert=True)
        return
    async with session_factory() as db:
        ac_repo = AccessCodeRepository(db)
        await ac_repo.upsert(code, label, selected)
        await db.commit()
    await state.clear()
    await call.answer("Сохранено")
    await safe_edit_text(
        call.message,
        f"Код <code>{escape(code)}</code> обновлён.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="<< Коды доступа", callback_data="ap:codes")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("ap:cdel:"))
async def handle_delete_code(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    code = call.data.split(":", 2)[2]
    async with session_factory() as db:
        ac_repo = AccessCodeRepository(db)
        await ac_repo.delete(code)
        await db.commit()
    await call.answer(f"Код '{code}' удалён")
    async with session_factory() as db:
        settings_repo = SettingsRepository(db)
        global_code = await settings_repo.get_or_create(ACCESS_CODE_KEY, "")
        await db.commit()
        ac_repo = AccessCodeRepository(db)
        codes = await ac_repo.list_all()
    rows: list[list[InlineKeyboardButton]] = []
    lines = [
        "<b>Коды доступа</b>\n",
        f"Глобальный код (все темы): <code>{escape(global_code)}</code>\n",
    ]
    if codes:
        lines.append("<b>Коды с ограничением тем:</b>")
        for ac in codes:
            topics_label = ", ".join(display_name(t) for t in (ac.allowed_topics or []))
            if len(topics_label) > 120:
                topics_label = f"{len(ac.allowed_topics)} тем"
            lines.append(f"- <code>{escape(ac.code)}</code> ({escape(ac.label)}): {topics_label}")
            rows.append(
                [
                    InlineKeyboardButton(text=f"Изменить: {ac.label}", callback_data=f"ap:cedit:{ac.code}"),
                    InlineKeyboardButton(text="Удалить", callback_data=f"ap:cdel:{ac.code}"),
                ]
            )
    else:
        lines.append("Пользовательских кодов пока нет.")
    rows.append([InlineKeyboardButton(text="➕ Создать код", callback_data="ap:cnew")])
    rows.append([InlineKeyboardButton(text="<< Панель", callback_data="ap:root")])
    await safe_edit_text(call.message, "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "ap:cats")
async def handle_cats_shortcut(
    call: CallbackQuery,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    await call.answer()
    await safe_edit_text(
        call.message,
        "Используй команду /categories для управления кастомными категориями.\n"
        "Вернуться: нажми кнопку ниже.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="<< Панель", callback_data="ap:root")]
            ]
        ),
    )


@router.callback_query(F.data == "ap:import")
async def handle_import_shortcut(
    call: CallbackQuery,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    await call.answer()
    await safe_edit_text(
        call.message,
        "Используй команду /import для импорта вопросов из JSON.\n"
        "Вернуться: нажми кнопку ниже.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="<< Панель", callback_data="ap:root")]
            ]
        ),
    )


@router.callback_query(F.data == "ap:reports")
async def handle_reports_shortcut(
    call: CallbackQuery,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    await call.answer()
    await safe_edit_text(
        call.message,
        "Используй команду /reports для просмотра открытых жалоб.\n"
        "Вернуться: нажми кнопку ниже.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="<< Панель", callback_data="ap:root")]
            ]
        ),
    )


@router.callback_query(F.data == "ap:dash")
async def handle_dash_shortcut(
    call: CallbackQuery,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    await call.answer()
    await safe_edit_text(
        call.message,
        "Используй команду /admin для просмотра дашборда.\n"
        "Вернуться: нажми кнопку ниже.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="<< Панель", callback_data="ap:root")]
            ]
        ),
    )


@router.callback_query(F.data == "ap:broadcast")
async def handle_broadcast_shortcut(
    call: CallbackQuery,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    await call.answer()
    await safe_edit_text(
        call.message,
        "Используй команды:\n"
        "- /broadcast_test ТЕКСТ - тестовая отправка себе\n"
        "- /broadcast ТЕКСТ - массовая рассылка всем юзерам\n\n"
        "Вернуться: нажми кнопку ниже.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="<< Панель", callback_data="ap:root")]
            ]
        ),
    )
