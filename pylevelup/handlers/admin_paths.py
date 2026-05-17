from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.categories import (
    CATEGORIES,
    CATEGORY_BY_KEY,
    custom_categories,
    display_name,
)
from pylevelup.config import Settings
from pylevelup.db.models import LearningPath
from pylevelup.repositories import LearningPathRepository
from pylevelup.utils.edit import safe_edit_text

router = Router(name="pylevelup_admin_paths")


class PathStates(StatesGroup):
    creating_slug = State()
    creating_title = State()
    creating_description = State()
    editing_title = State()
    editing_description = State()
    adding_step_title = State()
    adding_step_questions = State()
    adding_step_accuracy = State()


def _owner(user_id: int | None, settings: Settings) -> bool:
    return user_id is not None and user_id == settings.owner_telegram_id


def _paths_root_kb(paths: list[LearningPath]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in paths:
        suffix = "" if p.is_active else " (скрыт)"
        rows.append(
            [InlineKeyboardButton(text=f"{p.title}{suffix}", callback_data=f"app:view:{p.id}")]
        )
    rows.append([InlineKeyboardButton(text="➕ Создать план", callback_data="app:new")])
    rows.append([InlineKeyboardButton(text="<< Панель", callback_data="ap:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "app:list")
async def handle_paths_admin_list(
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
    await state.clear()
    async with session_factory() as db:
        paths = await LearningPathRepository(db).list_all()
    await call.answer()
    await safe_edit_text(
        call.message,
        "<b>Учебные планы</b>\n\nТык на план - редактировать. Или создай новый.",
        reply_markup=_paths_root_kb(paths),
    )


def _format_path_admin(path: LearningPath) -> str:
    steps = sorted(path.steps, key=lambda s: s.position)
    lines = [
        f"<b>{escape(path.title)}</b>",
        f"slug: <code>{escape(path.slug)}</code>",
        f"Статус: {'активен' if path.is_active else 'скрыт'}",
    ]
    if path.description:
        lines.append("")
        lines.append(escape(path.description))
    lines.append("")
    lines.append(f"Блоки ({len(steps)}):")
    if not steps:
        lines.append("- пока нет")
    for idx, step in enumerate(steps):
        label = step.title or display_name(step.topic_key)
        lines.append(
            f"{idx + 1}. {escape(label)} (<code>{escape(step.topic_key)}</code>) - "
            f"{step.required_questions} вопросов, ≥ {step.required_accuracy}%"
        )
    return "\n".join(lines)


def _path_admin_kb(path: LearningPath) -> InlineKeyboardMarkup:
    visibility = "✅ Активен" if path.is_active else "🚫 Скрыт"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="➕ Добавить блок", callback_data=f"app:addstep:{path.id}")],
    ]
    steps = sorted(path.steps, key=lambda s: s.position)
    for step in steps:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 Удалить блок {step.position + 1}",
                    callback_data=f"app:stepdel:{path.id}:{step.id}",
                )
            ]
        )
    rows.extend(
        [
            [InlineKeyboardButton(text="✏️ Название", callback_data=f"app:editt:{path.id}")],
            [InlineKeyboardButton(text="✏️ Описание", callback_data=f"app:editd:{path.id}")],
            [InlineKeyboardButton(text=f"{visibility}", callback_data=f"app:togg:{path.id}")],
            [InlineKeyboardButton(text="🗑 Удалить план", callback_data=f"app:delc:{path.id}")],
            [InlineKeyboardButton(text="<< К планам", callback_data="app:list")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_path_admin(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    path_id: int,
) -> None:
    if call.message is None:
        return
    async with session_factory() as db:
        path = await LearningPathRepository(db).get(path_id)
    if path is None:
        await safe_edit_text(call.message, "План не найден.")
        return
    await safe_edit_text(call.message, _format_path_admin(path), reply_markup=_path_admin_kb(path))


@router.callback_query(F.data.startswith("app:view:"))
async def handle_path_view_admin(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.message is None or call.data is None:
        await call.answer()
        return
    try:
        path_id = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    await state.clear()
    await call.answer()
    await _render_path_admin(call, session_factory, path_id)


@router.callback_query(F.data == "app:new")
async def handle_path_new_start(
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
    await state.set_state(PathStates.creating_slug)
    await call.answer()
    await safe_edit_text(
        call.message,
        "Введи <b>slug</b> плана (латиница, цифры, _; 3-32 символа). Пример: <code>junior_backend</code>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="app:list")]]
        ),
    )


@router.message(PathStates.creating_slug)
async def handle_path_new_slug(
    message: Message,
    settings: Settings,
    session_factory: async_sessionmaker,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    slug = (message.text or "").strip().lower()
    if not (3 <= len(slug) <= 32) or not all(c.isalnum() or c == "_" for c in slug):
        await message.answer("Неверный slug. Только латиница, цифры и _, 3-32 символа.")
        return
    async with session_factory() as db:
        existing = await LearningPathRepository(db).get_by_slug(slug)
    if existing is not None:
        await message.answer("План с таким slug уже есть.")
        return
    await state.update_data(new_path_slug=slug)
    await state.set_state(PathStates.creating_title)
    await message.answer("Введи <b>название</b> плана (3-64 символа).")


@router.message(PathStates.creating_title)
async def handle_path_new_title(
    message: Message,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    title = (message.text or "").strip()
    if not (3 <= len(title) <= 64):
        await message.answer("Название 3-64 символа.")
        return
    await state.update_data(new_path_title=title)
    await state.set_state(PathStates.creating_description)
    await message.answer(
        "Введи <b>описание</b> плана (или <code>-</code> чтобы пропустить)."
    )


@router.message(PathStates.creating_description)
async def handle_path_new_description(
    message: Message,
    settings: Settings,
    session_factory: async_sessionmaker,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    raw = (message.text or "").strip()
    description: str | None = None if raw == "-" else raw
    data = await state.get_data()
    slug = data.get("new_path_slug")
    title = data.get("new_path_title")
    if not isinstance(slug, str) or not isinstance(title, str):
        await state.clear()
        return
    async with session_factory() as db:
        path = await LearningPathRepository(db).create(
            slug=slug, title=title, description=description
        )
        await db.commit()
        path_id = path.id
    await state.clear()
    await message.answer(
        f"План <b>{escape(title)}</b> создан. Добавь блоки в редакторе.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📝 Открыть", callback_data=f"app:view:{path_id}")]
            ]
        ),
    )


@router.callback_query(F.data.startswith("app:togg:"))
async def handle_path_toggle(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.message is None or call.data is None:
        await call.answer()
        return
    try:
        path_id = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        repo = LearningPathRepository(db)
        path = await repo.get(path_id)
        if path is None:
            await call.answer("План не найден", show_alert=True)
            return
        await repo.update(path_id, is_active=not path.is_active)
        await db.commit()
    await call.answer("Видимость обновлена")
    await _render_path_admin(call, session_factory, path_id)


@router.callback_query(F.data.startswith("app:editt:"))
async def handle_path_edit_title_start(
    call: CallbackQuery,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.message is None or call.data is None:
        await call.answer()
        return
    try:
        path_id = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    await state.set_state(PathStates.editing_title)
    await state.update_data(edit_path_id=path_id)
    await call.answer()
    await safe_edit_text(
        call.message,
        "Пришли новое <b>название</b> плана (3-64 символа).",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Отмена", callback_data=f"app:view:{path_id}")]
            ]
        ),
    )


@router.message(PathStates.editing_title)
async def handle_path_edit_title_input(
    message: Message,
    settings: Settings,
    session_factory: async_sessionmaker,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    title = (message.text or "").strip()
    if not (3 <= len(title) <= 64):
        await message.answer("3-64 символа.")
        return
    data = await state.get_data()
    path_id = data.get("edit_path_id")
    if not isinstance(path_id, int):
        await state.clear()
        return
    async with session_factory() as db:
        await LearningPathRepository(db).update(path_id, title=title)
        await db.commit()
        path = await LearningPathRepository(db).get(path_id)
    await state.clear()
    if path is None:
        return
    await message.answer(_format_path_admin(path), reply_markup=_path_admin_kb(path))


@router.callback_query(F.data.startswith("app:editd:"))
async def handle_path_edit_desc_start(
    call: CallbackQuery,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.message is None or call.data is None:
        await call.answer()
        return
    try:
        path_id = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    await state.set_state(PathStates.editing_description)
    await state.update_data(edit_path_id=path_id)
    await call.answer()
    await safe_edit_text(
        call.message,
        "Пришли новое <b>описание</b> (или <code>-</code> чтобы очистить).",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Отмена", callback_data=f"app:view:{path_id}")]
            ]
        ),
    )


@router.message(PathStates.editing_description)
async def handle_path_edit_desc_input(
    message: Message,
    settings: Settings,
    session_factory: async_sessionmaker,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    raw = (message.text or "").strip()
    description: str | None = None if raw == "-" else raw
    data = await state.get_data()
    path_id = data.get("edit_path_id")
    if not isinstance(path_id, int):
        await state.clear()
        return
    async with session_factory() as db:
        repo = LearningPathRepository(db)
        await repo.update(path_id, description=description)
        if description is None:
            path = await repo.get(path_id)
            if path is not None:
                path.description = None
        await db.commit()
        path = await repo.get(path_id)
    await state.clear()
    if path is None:
        return
    await message.answer(_format_path_admin(path), reply_markup=_path_admin_kb(path))


@router.callback_query(F.data.startswith("app:delc:"))
async def handle_path_delete_confirm(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.message is None or call.data is None:
        await call.answer()
        return
    try:
        path_id = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        path = await LearningPathRepository(db).get(path_id)
    if path is None:
        await call.answer("Не найден", show_alert=True)
        return
    await call.answer()
    text = (
        f"<b>Удалить план {escape(path.title)}?</b>\n\n"
        f"Будут удалены все блоки ({len(path.steps)}) и прогресс юзеров по нему. "
        "Сами вопросы не трогаем.\nТочно?"
    )
    rows = [
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"app:del:{path_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"app:view:{path_id}")],
    ]
    await safe_edit_text(call.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("app:del:"))
async def handle_path_delete(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.message is None or call.data is None:
        await call.answer()
        return
    try:
        path_id = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        removed = await LearningPathRepository(db).delete(path_id)
        await db.commit()
    if not removed:
        await call.answer("Не найден", show_alert=True)
        return
    await call.answer("Удалён")
    async with session_factory() as db:
        paths = await LearningPathRepository(db).list_all()
    await safe_edit_text(
        call.message,
        "План удалён.\n\n<b>Учебные планы</b>",
        reply_markup=_paths_root_kb(paths),
    )


def _topic_pick_kb(path_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    keys: list[str] = list(CATEGORY_BY_KEY.keys())
    for cat in custom_categories():
        if cat.key not in keys:
            keys.append(cat.key)
    for k in keys:
        title = display_name(k)
        rows.append(
            [InlineKeyboardButton(text=title, callback_data=f"app:steptopic:{path_id}:{k}")]
        )
    rows.append([InlineKeyboardButton(text="Отмена", callback_data=f"app:view:{path_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("app:addstep:"))
async def handle_step_add_start(
    call: CallbackQuery,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.message is None or call.data is None:
        await call.answer()
        return
    try:
        path_id = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    _ = [c for c in CATEGORIES]
    await state.clear()
    await call.answer()
    await safe_edit_text(
        call.message,
        "Выбери <b>тему</b> для нового блока:",
        reply_markup=_topic_pick_kb(path_id),
    )


@router.callback_query(F.data.startswith("app:steptopic:"))
async def handle_step_add_topic(
    call: CallbackQuery,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.message is None or call.data is None:
        await call.answer()
        return
    parts = call.data.split(":", 3)
    if len(parts) != 4:
        await call.answer()
        return
    try:
        path_id = int(parts[2])
    except ValueError:
        await call.answer()
        return
    topic_key = parts[3]
    await state.update_data(step_path_id=path_id, step_topic_key=topic_key)
    await state.set_state(PathStates.adding_step_title)
    await call.answer()
    await safe_edit_text(
        call.message,
        "Пришли <b>название блока</b> (или <code>-</code>, чтобы использовать название темы).",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Отмена", callback_data=f"app:view:{path_id}")]
            ]
        ),
    )


@router.message(PathStates.adding_step_title)
async def handle_step_add_title(
    message: Message,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    raw = (message.text or "").strip()
    title: str | None = None if raw == "-" else raw
    if title is not None and not (1 <= len(title) <= 128):
        await message.answer("Название 1-128 символов или <code>-</code>.")
        return
    await state.update_data(step_title=title)
    await state.set_state(PathStates.adding_step_questions)
    await message.answer(
        "Сколько <b>вопросов</b> юзер должен решить в этой теме, чтобы блок засчитался? (1-200)"
    )


@router.message(PathStates.adding_step_questions)
async def handle_step_add_questions(
    message: Message,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    try:
        value = int((message.text or "").strip())
    except ValueError:
        await message.answer("Нужно число 1-200.")
        return
    if not 1 <= value <= 200:
        await message.answer("Диапазон 1-200.")
        return
    await state.update_data(step_questions=value)
    await state.set_state(PathStates.adding_step_accuracy)
    await message.answer("С какой <b>точностью</b> (%) считать блок пройденным? (40-100)")


@router.message(PathStates.adding_step_accuracy)
async def handle_step_add_accuracy(
    message: Message,
    settings: Settings,
    session_factory: async_sessionmaker,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    try:
        value = int((message.text or "").strip())
    except ValueError:
        await message.answer("Нужно число 40-100.")
        return
    if not 40 <= value <= 100:
        await message.answer("Диапазон 40-100.")
        return
    data = await state.get_data()
    path_id = data.get("step_path_id")
    topic_key = data.get("step_topic_key")
    title = data.get("step_title")
    questions = data.get("step_questions")
    if (
        not isinstance(path_id, int)
        or not isinstance(topic_key, str)
        or not isinstance(questions, int)
    ):
        await state.clear()
        return
    async with session_factory() as db:
        await LearningPathRepository(db).add_step(
            path_id=path_id,
            topic_key=topic_key,
            title=title if isinstance(title, str) else None,
            required_questions=questions,
            required_accuracy=value,
        )
        await db.commit()
        path = await LearningPathRepository(db).get(path_id)
    await state.clear()
    if path is None:
        return
    await message.answer(_format_path_admin(path), reply_markup=_path_admin_kb(path))


@router.callback_query(F.data.startswith("app:stepdel:"))
async def handle_step_delete(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.message is None or call.data is None:
        await call.answer()
        return
    parts = call.data.split(":")
    if len(parts) != 4:
        await call.answer()
        return
    try:
        path_id = int(parts[2])
        step_id = int(parts[3])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        await LearningPathRepository(db).delete_step(step_id)
        await db.commit()
    await call.answer("Блок удалён")
    await _render_path_admin(call, session_factory, path_id)
