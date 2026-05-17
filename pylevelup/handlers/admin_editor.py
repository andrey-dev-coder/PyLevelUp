import json
import re
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
from pylevelup.db.models import OpenQuestion, Question
from pylevelup.repositories import OpenQuestionRepository, QuestionRepository
from pylevelup.utils.edit import safe_edit_text

router = Router(name="pylevelup_admin_editor")

PAGE_SIZE = 10
PREVIEW_LEN = 50


class EditorStates(StatesGroup):
    editing_q_text = State()
    editing_q_options = State()
    editing_q_explanation = State()
    editing_q_difficulty = State()
    editing_q_code = State()
    editing_q_code_lang = State()
    editing_t_text = State()
    editing_t_answer = State()
    editing_t_checklist = State()
    editing_t_difficulty = State()
    editing_t_code = State()
    editing_t_code_lang = State()
    searching_q_all = State()
    searching_q_topic = State()
    searching_t_all = State()
    searching_t_topic = State()


SEARCH_LIMIT = 20


def _owner(user_id: int | None, settings: Settings) -> bool:
    return user_id is not None and user_id == settings.owner_telegram_id


def _all_categories_kb() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🔍 Поиск по всем вопросам", callback_data="ape:qsearch:all")],
        [InlineKeyboardButton(text="🔍 Поиск по всей теории", callback_data="ape:tsearch:all")],
    ]
    for cat in CATEGORIES:
        rows.append(
            [InlineKeyboardButton(text=cat.title, callback_data=f"ape:cat:{cat.key}")]
        )
    for cat in custom_categories():
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{cat.title} (своя)",
                    callback_data=f"ape:cat:{cat.key}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="<< Панель", callback_data="ap:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "ape:cats")
async def handle_editor_root(
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
    await state.clear()
    await call.answer()
    await safe_edit_text(
        call.message,
        "<b>Редактор вопросов</b>\n\n"
        "Выбери категорию. Дальше можно править/скрывать/удалять отдельные вопросы.",
        reply_markup=_all_categories_kb(),
    )


def _category_actions_kb(key: str, test_count: int, theory_count: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"📝 Тестовые вопросы ({test_count})",
                callback_data=f"ape:qlist:{key}:0",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"📚 Теория ({theory_count})",
                callback_data=f"ape:tlist:{key}:0",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔍 Поиск в категории",
                callback_data=f"ape:qsearch:cat:{key}",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔍 Поиск по теории",
                callback_data=f"ape:tsearch:cat:{key}",
            )
        ],
    ]
    if key not in CATEGORY_BY_KEY:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 Удалить категорию",
                    callback_data=f"ap:catview:{key}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="<< Категории", callback_data="ape:cats")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("ape:cat:"))
async def handle_editor_category(
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
    key = call.data.split(":", 2)[2]
    if key not in CATEGORY_BY_KEY and not any(c.key == key for c in custom_categories()):
        await call.answer("Категория не найдена", show_alert=True)
        return
    await state.clear()
    async with session_factory() as db:
        test_count = await QuestionRepository(db).count_by_topic(key)
        theory_count = await OpenQuestionRepository(db).count_by_topic(key)
    await call.answer()
    title = escape(display_name(key))
    text = (
        f"<b>Категория:</b> {title}\n"
        f"<b>Ключ:</b> <code>{escape(key)}</code>\n\n"
        f"Тестовых вопросов: {test_count}\n"
        f"Теоретических карточек: {theory_count}\n\n"
        "Что хочешь делать?"
    )
    await safe_edit_text(
        call.message,
        text,
        reply_markup=_category_actions_kb(key, test_count, theory_count),
    )


def _short_preview(text: str) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) > PREVIEW_LEN:
        text = text[: PREVIEW_LEN - 1] + "…"
    return text


def _qlist_kb(key: str, page: int, items: list[Question], total: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for q in items:
        marker = "🚫 " if not q.is_active else ""
        label = f"{marker}#{q.id} {_short_preview(q.text)}"
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"ape:qview:{q.id}")]
        )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="<< Назад",
                callback_data=f"ape:qlist:{key}:{page - 1}",
            )
        )
    if (page + 1) * PAGE_SIZE < total:
        nav.append(
            InlineKeyboardButton(
                text="Вперёд >>",
                callback_data=f"ape:qlist:{key}:{page + 1}",
            )
        )
    if nav:
        rows.append(nav)
    rows.append(
        [InlineKeyboardButton(text="🔍 Поиск", callback_data=f"ape:qsearch:cat:{key}")]
    )
    rows.append([InlineKeyboardButton(text="<< Категория", callback_data=f"ape:cat:{key}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("ape:qlist:"))
async def handle_qlist(
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
    parts = call.data.split(":")
    if len(parts) != 4:
        await call.answer()
        return
    key = parts[2]
    try:
        page = int(parts[3])
    except ValueError:
        page = 0
    async with session_factory() as db:
        repo = QuestionRepository(db)
        items = await repo.list_by_topic(key, offset=page * PAGE_SIZE, limit=PAGE_SIZE)
        total = await repo.count_by_topic(key)
    await call.answer()
    if total == 0:
        await safe_edit_text(
            call.message,
            f"<b>{escape(display_name(key))}</b>\n\nПока нет тестовых вопросов.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="<< Категория", callback_data=f"ape:cat:{key}")]
                ]
            ),
        )
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    text = (
        f"<b>{escape(display_name(key))} - тестовые вопросы</b>\n"
        f"Всего: {total} | стр. {page + 1}/{total_pages}\n\n"
        "Тыкни на вопрос, чтобы посмотреть/изменить."
    )
    await safe_edit_text(call.message, text, reply_markup=_qlist_kb(key, page, items, total))


def _format_question(q: Question) -> str:
    parts: list[str] = [
        f"<b>Вопрос #{q.id}</b>",
        f"Категория: {escape(display_name(q.topic))}",
        f"Сложность: {q.difficulty}",
        f"Статус: {'активен' if q.is_active else '<u>скрыт</u>'}",
        "",
        f"<b>Текст:</b>\n{escape(q.text)}",
    ]
    if q.code:
        lang = q.code_language or "plain"
        parts.append("")
        parts.append(f"<b>Код ({escape(lang)}):</b>")
        parts.append(f"<pre>{escape(q.code)}</pre>")
    parts.append("")
    parts.append("<b>Варианты:</b>")
    for idx, opt in enumerate(q.options):
        marker = "✓ " if idx == q.correct_index else "  "
        parts.append(f"{marker}{idx}. {escape(opt)}")
    if q.explanation:
        parts.append("")
        parts.append(f"<b>Пояснение:</b> {escape(q.explanation)}")
    return "\n".join(parts)


def _qview_kb(q: Question) -> InlineKeyboardMarkup:
    hide_text = "✅ Активировать" if not q.is_active else "🚫 Скрыть"
    code_label = "✏️ Код" if not q.code else "✏️ Код ✓"
    rows = [
        [InlineKeyboardButton(text="✏️ Текст", callback_data=f"ape:qe:{q.id}:text")],
        [InlineKeyboardButton(text="✏️ Варианты", callback_data=f"ape:qe:{q.id}:opts")],
        [InlineKeyboardButton(text="✏️ Правильный ответ", callback_data=f"ape:qcorrect:{q.id}")],
        [InlineKeyboardButton(text="✏️ Пояснение", callback_data=f"ape:qe:{q.id}:expl")],
        [InlineKeyboardButton(text="✏️ Сложность", callback_data=f"ape:qe:{q.id}:diff")],
        [
            InlineKeyboardButton(text=code_label, callback_data=f"ape:qe:{q.id}:code"),
            InlineKeyboardButton(text="✏️ Язык", callback_data=f"ape:qe:{q.id}:lang"),
        ],
        [InlineKeyboardButton(text=hide_text, callback_data=f"ape:qhide:{q.id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"ape:qdelc:{q.id}")],
        [InlineKeyboardButton(text="<< К списку", callback_data=f"ape:qlist:{q.topic}:0")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_qview(call: CallbackQuery, session_factory: async_sessionmaker, qid: int) -> None:
    if call.message is None:
        return
    async with session_factory() as db:
        q = await QuestionRepository(db).get_by_id(qid)
    if q is None:
        await safe_edit_text(call.message, "Вопрос не найден.")
        return
    await safe_edit_text(call.message, _format_question(q), reply_markup=_qview_kb(q))


@router.callback_query(F.data.startswith("ape:qview:"))
async def handle_qview(
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
    try:
        qid = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    await state.clear()
    await call.answer()
    await _show_qview(call, session_factory, qid)


@router.callback_query(F.data.startswith("ape:qhide:"))
async def handle_qhide(
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
        qid = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        repo = QuestionRepository(db)
        q = await repo.get_by_id(qid)
        if q is None:
            await call.answer("Не найден", show_alert=True)
            return
        await repo.set_active(qid, not q.is_active)
        await db.commit()
    await call.answer("Скрыт" if q.is_active else "Активирован")
    await _show_qview(call, session_factory, qid)


@router.callback_query(F.data.startswith("ape:qdelc:"))
async def handle_qdelete_confirm(
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
        qid = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        q = await QuestionRepository(db).get_by_id(qid)
    if q is None:
        await call.answer("Не найден", show_alert=True)
        return
    await call.answer()
    text = (
        f"<b>Удалить вопрос #{qid}?</b>\n\n"
        f"{escape(_short_preview(q.text))}\n\n"
        "Удаление каскадно сотрёт все попытки и закладки этого вопроса. Точно?"
    )
    rows = [
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"ape:qdel:{qid}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"ape:qview:{qid}")],
    ]
    await safe_edit_text(call.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("ape:qdel:"))
async def handle_qdelete(
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
        qid = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        repo = QuestionRepository(db)
        q = await repo.get_by_id(qid)
        topic = q.topic if q else None
        removed = await repo.delete_one(qid)
        await db.commit()
    if not removed:
        await call.answer("Не найден", show_alert=True)
        return
    await call.answer("Удалён")
    await safe_edit_text(
        call.message,
        f"Вопрос #{qid} удалён.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="<< К списку",
                        callback_data=f"ape:qlist:{topic}:0" if topic else "ape:cats",
                    )
                ]
            ]
        ),
    )


def _qcorrect_kb(q: Question) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for idx, opt in enumerate(q.options):
        marker = "✓ " if idx == q.correct_index else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker}{idx}. {_short_preview(opt)}",
                    callback_data=f"ape:qcorset:{q.id}:{idx}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="<< Назад", callback_data=f"ape:qview:{q.id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("ape:qcorrect:"))
async def handle_qcorrect(
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
        qid = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        q = await QuestionRepository(db).get_by_id(qid)
    if q is None:
        await call.answer("Не найден", show_alert=True)
        return
    await call.answer()
    text = (
        f"<b>Вопрос #{qid}</b>\n\n"
        f"{escape(q.text)}\n\n"
        "Выбери правильный ответ:"
    )
    await safe_edit_text(call.message, text, reply_markup=_qcorrect_kb(q))


@router.callback_query(F.data.startswith("ape:qcorset:"))
async def handle_qcorrect_set(
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
    parts = call.data.split(":")
    if len(parts) != 4:
        await call.answer()
        return
    try:
        qid = int(parts[2])
        new_idx = int(parts[3])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        repo = QuestionRepository(db)
        q = await repo.get_by_id(qid)
        if q is None:
            await call.answer("Не найден", show_alert=True)
            return
        if not (0 <= new_idx < len(q.options)):
            await call.answer("Неверный индекс", show_alert=True)
            return
        await repo.update_fields(qid, correct_index=new_idx)
        await db.commit()
    await call.answer("Правильный ответ обновлён")
    await _show_qview(call, session_factory, qid)


_FIELD_PROMPTS_Q = {
    "text": "Пришли новый <b>текст вопроса</b>.",
    "opts": (
        "Пришли <b>варианты</b> как JSON-массив строк (2-6 шт).\n"
        "Пример: <code>[\"True\", \"False\", \"Error\", \"None\"]</code>"
    ),
    "expl": "Пришли новое <b>пояснение</b>. Чтобы очистить - отправь <code>-</code>.",
    "diff": "Пришли новую <b>сложность</b> от 1 до 5.",
    "code": (
        "Пришли <b>блок кода</b> (один или несколько строк, до 4096 символов). "
        "Чтобы убрать блок - отправь <code>-</code>."
    ),
    "lang": (
        "Пришли <b>язык кода</b> для подсветки (например <code>python</code>, "
        "<code>sql</code>, <code>js</code>). Чтобы очистить - отправь <code>-</code>."
    ),
}

_FIELD_STATE_Q = {
    "text": EditorStates.editing_q_text,
    "opts": EditorStates.editing_q_options,
    "expl": EditorStates.editing_q_explanation,
    "diff": EditorStates.editing_q_difficulty,
    "code": EditorStates.editing_q_code,
    "lang": EditorStates.editing_q_code_lang,
}


@router.callback_query(F.data.startswith("ape:qe:"))
async def handle_qedit_field(
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
    parts = call.data.split(":")
    if len(parts) != 4:
        await call.answer()
        return
    try:
        qid = int(parts[2])
    except ValueError:
        await call.answer()
        return
    field = parts[3]
    if field not in _FIELD_PROMPTS_Q:
        await call.answer()
        return
    await state.set_state(_FIELD_STATE_Q[field])
    await state.update_data(edit_target_id=qid)
    await call.answer()
    await safe_edit_text(
        call.message,
        _FIELD_PROMPTS_Q[field],
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Отмена", callback_data=f"ape:qview:{qid}")]
            ]
        ),
    )


@router.message(EditorStates.editing_q_text)
async def handle_qedit_text_input(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    text = (message.text or "").strip()
    if len(text) < 3 or len(text) > 4096:
        await message.answer("Текст должен быть 3-4096 символов. Попробуй ещё раз.")
        return
    data = await state.get_data()
    qid = data.get("edit_target_id")
    if not isinstance(qid, int):
        await state.clear()
        return
    async with session_factory() as db:
        await QuestionRepository(db).update_fields(qid, text=text)
        await db.commit()
        q = await QuestionRepository(db).get_by_id(qid)
    await state.clear()
    if q is None:
        await message.answer("Вопрос не найден.")
        return
    await message.answer(_format_question(q), reply_markup=_qview_kb(q))


@router.message(EditorStates.editing_q_options)
async def handle_qedit_options_input(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    raw = (message.text or "").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        await message.answer("Не похоже на JSON. Пришли массив строк, например <code>[\"A\", \"B\"]</code>.")
        return
    if not isinstance(parsed, list) or not all(isinstance(o, str) for o in parsed):
        await message.answer("Нужен массив строк.")
        return
    if not 2 <= len(parsed) <= 6:
        await message.answer("От 2 до 6 вариантов.")
        return
    data = await state.get_data()
    qid = data.get("edit_target_id")
    if not isinstance(qid, int):
        await state.clear()
        return
    async with session_factory() as db:
        repo = QuestionRepository(db)
        q = await repo.get_by_id(qid)
        if q is None:
            await state.clear()
            await message.answer("Вопрос не найден.")
            return
        new_correct = q.correct_index
        if new_correct >= len(parsed):
            new_correct = 0
        await repo.update_fields(qid, options=parsed, correct_index=new_correct)
        await db.commit()
        q = await repo.get_by_id(qid)
    await state.clear()
    if q is None:
        return
    note = ""
    if new_correct != q.correct_index:
        note = "\n\n<i>Внимание: индекс правильного ответа был сброшен на 0, проверь.</i>"
    await message.answer(_format_question(q) + note, reply_markup=_qview_kb(q))


@router.message(EditorStates.editing_q_explanation)
async def handle_qedit_explanation_input(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    raw = (message.text or "").strip()
    new_value: str | None = None if raw == "-" else raw
    if new_value is not None and len(new_value) > 4096:
        await message.answer("Пояснение до 4096 символов.")
        return
    data = await state.get_data()
    qid = data.get("edit_target_id")
    if not isinstance(qid, int):
        await state.clear()
        return
    async with session_factory() as db:
        await QuestionRepository(db).update_fields(qid, explanation=new_value or "")
        if new_value is None:
            q = await QuestionRepository(db).get_by_id(qid)
            if q is not None:
                q.explanation = None
        await db.commit()
        q = await QuestionRepository(db).get_by_id(qid)
    await state.clear()
    if q is None:
        return
    await message.answer(_format_question(q), reply_markup=_qview_kb(q))


@router.message(EditorStates.editing_q_difficulty)
async def handle_qedit_difficulty_input(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    raw = (message.text or "").strip()
    try:
        value = int(raw)
    except ValueError:
        await message.answer("Нужно число от 1 до 5.")
        return
    if not 1 <= value <= 5:
        await message.answer("Только 1-5.")
        return
    data = await state.get_data()
    qid = data.get("edit_target_id")
    if not isinstance(qid, int):
        await state.clear()
        return
    async with session_factory() as db:
        await QuestionRepository(db).update_fields(qid, difficulty=value)
        await db.commit()
        q = await QuestionRepository(db).get_by_id(qid)
    await state.clear()
    if q is None:
        return
    await message.answer(_format_question(q), reply_markup=_qview_kb(q))


@router.message(EditorStates.editing_q_code)
async def handle_qedit_code_input(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    raw = (message.text or "").rstrip("\n")
    new_value: str | None = None if raw.strip() == "-" else raw
    if new_value is not None and len(new_value) > 4096:
        await message.answer("Блок кода до 4096 символов.")
        return
    data = await state.get_data()
    qid = data.get("edit_target_id")
    if not isinstance(qid, int):
        await state.clear()
        return
    async with session_factory() as db:
        await QuestionRepository(db).update_code(qid, code=new_value)
        await db.commit()
        q = await QuestionRepository(db).get_by_id(qid)
    await state.clear()
    if q is None:
        return
    await message.answer(_format_question(q), reply_markup=_qview_kb(q))


@router.message(EditorStates.editing_q_code_lang)
async def handle_qedit_code_lang_input(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    raw = (message.text or "").strip().lower()
    new_value: str | None
    if raw == "-" or not raw:
        new_value = None
    elif not re.fullmatch(r"[a-z0-9_+-]{1,32}", raw):
        await message.answer(
            "Язык должен быть короткой строкой (a-z, 0-9, _ + -). Например python, sql, js."
        )
        return
    else:
        new_value = raw
    data = await state.get_data()
    qid = data.get("edit_target_id")
    if not isinstance(qid, int):
        await state.clear()
        return
    async with session_factory() as db:
        await QuestionRepository(db).update_code_language(qid, code_language=new_value)
        await db.commit()
        q = await QuestionRepository(db).get_by_id(qid)
    await state.clear()
    if q is None:
        return
    await message.answer(_format_question(q), reply_markup=_qview_kb(q))


def _tlist_kb(key: str, page: int, items: list[OpenQuestion], total: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for t in items:
        marker = "🚫 " if not t.is_active else ""
        label = f"{marker}#{t.id} {_short_preview(t.text)}"
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"ape:tview:{t.id}")]
        )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="<< Назад",
                callback_data=f"ape:tlist:{key}:{page - 1}",
            )
        )
    if (page + 1) * PAGE_SIZE < total:
        nav.append(
            InlineKeyboardButton(
                text="Вперёд >>",
                callback_data=f"ape:tlist:{key}:{page + 1}",
            )
        )
    if nav:
        rows.append(nav)
    rows.append(
        [InlineKeyboardButton(text="🔍 Поиск", callback_data=f"ape:tsearch:cat:{key}")]
    )
    rows.append([InlineKeyboardButton(text="<< Категория", callback_data=f"ape:cat:{key}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("ape:tlist:"))
async def handle_tlist(
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
    parts = call.data.split(":")
    if len(parts) != 4:
        await call.answer()
        return
    key = parts[2]
    try:
        page = int(parts[3])
    except ValueError:
        page = 0
    async with session_factory() as db:
        repo = OpenQuestionRepository(db)
        items = await repo.list_by_topic(key, offset=page * PAGE_SIZE, limit=PAGE_SIZE)
        total = await repo.count_by_topic(key)
    await call.answer()
    if total == 0:
        await safe_edit_text(
            call.message,
            f"<b>{escape(display_name(key))}</b>\n\nПока нет теоретических карточек.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="<< Категория", callback_data=f"ape:cat:{key}")]
                ]
            ),
        )
        return
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    text = (
        f"<b>{escape(display_name(key))} - теория</b>\n"
        f"Всего: {total} | стр. {page + 1}/{total_pages}\n\n"
        "Тыкни на карточку для редактирования."
    )
    await safe_edit_text(call.message, text, reply_markup=_tlist_kb(key, page, items, total))


def _format_theory(t: OpenQuestion) -> str:
    parts: list[str] = [
        f"<b>Карточка #{t.id}</b>",
        f"Категория: {escape(display_name(t.topic))}",
        f"Сложность: {t.difficulty}",
        f"Статус: {'активна' if t.is_active else '<u>скрыта</u>'}",
        "",
        f"<b>Вопрос:</b>\n{escape(t.text)}",
    ]
    if t.code:
        lang = t.code_language or "plain"
        parts.append("")
        parts.append(f"<b>Код ({escape(lang)}):</b>")
        parts.append(f"<pre>{escape(t.code)}</pre>")
    parts.append("")
    parts.append(f"<b>Эталонный ответ:</b>\n{escape(t.ideal_answer)}")
    if t.checklist:
        parts.append("")
        parts.append("<b>Чек-лист:</b>")
        for item in t.checklist:
            parts.append(f"- {escape(item)}")
    return "\n".join(parts)


def _tview_kb(t: OpenQuestion) -> InlineKeyboardMarkup:
    hide_text = "✅ Активировать" if not t.is_active else "🚫 Скрыть"
    code_label = "✏️ Код" if not t.code else "✏️ Код ✓"
    rows = [
        [InlineKeyboardButton(text="✏️ Текст", callback_data=f"ape:te:{t.id}:text")],
        [InlineKeyboardButton(text="✏️ Эталонный ответ", callback_data=f"ape:te:{t.id}:ans")],
        [InlineKeyboardButton(text="✏️ Чек-лист", callback_data=f"ape:te:{t.id}:chk")],
        [InlineKeyboardButton(text="✏️ Сложность", callback_data=f"ape:te:{t.id}:diff")],
        [
            InlineKeyboardButton(text=code_label, callback_data=f"ape:te:{t.id}:code"),
            InlineKeyboardButton(text="✏️ Язык", callback_data=f"ape:te:{t.id}:lang"),
        ],
        [InlineKeyboardButton(text=hide_text, callback_data=f"ape:thide:{t.id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"ape:tdelc:{t.id}")],
        [InlineKeyboardButton(text="<< К списку", callback_data=f"ape:tlist:{t.topic}:0")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_tview(call: CallbackQuery, session_factory: async_sessionmaker, tid: int) -> None:
    if call.message is None:
        return
    async with session_factory() as db:
        t = await OpenQuestionRepository(db).get(tid)
    if t is None:
        await safe_edit_text(call.message, "Карточка не найдена.")
        return
    await safe_edit_text(call.message, _format_theory(t), reply_markup=_tview_kb(t))


@router.callback_query(F.data.startswith("ape:tview:"))
async def handle_tview(
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
    try:
        tid = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    await state.clear()
    await call.answer()
    await _show_tview(call, session_factory, tid)


@router.callback_query(F.data.startswith("ape:thide:"))
async def handle_thide(
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
        tid = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        repo = OpenQuestionRepository(db)
        t = await repo.get(tid)
        if t is None:
            await call.answer("Не найдена", show_alert=True)
            return
        await repo.set_active(tid, not t.is_active)
        await db.commit()
    await call.answer("Скрыта" if t.is_active else "Активирована")
    await _show_tview(call, session_factory, tid)


@router.callback_query(F.data.startswith("ape:tdelc:"))
async def handle_tdelete_confirm(
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
        tid = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        t = await OpenQuestionRepository(db).get(tid)
    if t is None:
        await call.answer("Не найдена", show_alert=True)
        return
    await call.answer()
    text = (
        f"<b>Удалить карточку #{tid}?</b>\n\n"
        f"{escape(_short_preview(t.text))}\n\n"
        "Действие необратимо. Точно?"
    )
    rows = [
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"ape:tdel:{tid}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"ape:tview:{tid}")],
    ]
    await safe_edit_text(call.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("ape:tdel:"))
async def handle_tdelete(
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
        tid = int(call.data.split(":")[2])
    except ValueError:
        await call.answer()
        return
    async with session_factory() as db:
        repo = OpenQuestionRepository(db)
        t = await repo.get(tid)
        topic = t.topic if t else None
        removed = await repo.delete_one(tid)
        await db.commit()
    if not removed:
        await call.answer("Не найдена", show_alert=True)
        return
    await call.answer("Удалена")
    await safe_edit_text(
        call.message,
        f"Карточка #{tid} удалена.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="<< К списку",
                        callback_data=f"ape:tlist:{topic}:0" if topic else "ape:cats",
                    )
                ]
            ]
        ),
    )


_FIELD_PROMPTS_T = {
    "text": "Пришли новый <b>текст</b> карточки.",
    "ans": "Пришли новый <b>эталонный ответ</b>.",
    "chk": (
        "Пришли <b>чек-лист</b> как JSON-массив строк (или <code>-</code> чтобы очистить).\n"
        "Пример: <code>[\"Упомянуть GIL\", \"Потоки vs процессы\"]</code>"
    ),
    "diff": "Пришли новую <b>сложность</b> от 1 до 5.",
    "code": (
        "Пришли <b>блок кода</b> (до 4096 символов). Чтобы убрать - отправь <code>-</code>."
    ),
    "lang": (
        "Пришли <b>язык кода</b> (например <code>python</code>). "
        "Чтобы очистить - отправь <code>-</code>."
    ),
}

_FIELD_STATE_T = {
    "text": EditorStates.editing_t_text,
    "ans": EditorStates.editing_t_answer,
    "chk": EditorStates.editing_t_checklist,
    "diff": EditorStates.editing_t_difficulty,
    "code": EditorStates.editing_t_code,
    "lang": EditorStates.editing_t_code_lang,
}


@router.callback_query(F.data.startswith("ape:te:"))
async def handle_tedit_field(
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
    parts = call.data.split(":")
    if len(parts) != 4:
        await call.answer()
        return
    try:
        tid = int(parts[2])
    except ValueError:
        await call.answer()
        return
    field = parts[3]
    if field not in _FIELD_PROMPTS_T:
        await call.answer()
        return
    await state.set_state(_FIELD_STATE_T[field])
    await state.update_data(edit_target_id=tid)
    await call.answer()
    await safe_edit_text(
        call.message,
        _FIELD_PROMPTS_T[field],
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Отмена", callback_data=f"ape:tview:{tid}")]
            ]
        ),
    )


@router.message(EditorStates.editing_t_text)
async def handle_tedit_text_input(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    text = (message.text or "").strip()
    if len(text) < 3 or len(text) > 4096:
        await message.answer("Текст 3-4096 символов.")
        return
    data = await state.get_data()
    tid = data.get("edit_target_id")
    if not isinstance(tid, int):
        await state.clear()
        return
    async with session_factory() as db:
        await OpenQuestionRepository(db).update_fields(tid, text=text)
        await db.commit()
        t = await OpenQuestionRepository(db).get(tid)
    await state.clear()
    if t is None:
        return
    await message.answer(_format_theory(t), reply_markup=_tview_kb(t))


@router.message(EditorStates.editing_t_answer)
async def handle_tedit_answer_input(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    text = (message.text or "").strip()
    if len(text) < 3:
        await message.answer("Слишком короткий ответ.")
        return
    data = await state.get_data()
    tid = data.get("edit_target_id")
    if not isinstance(tid, int):
        await state.clear()
        return
    async with session_factory() as db:
        await OpenQuestionRepository(db).update_fields(tid, ideal_answer=text)
        await db.commit()
        t = await OpenQuestionRepository(db).get(tid)
    await state.clear()
    if t is None:
        return
    await message.answer(_format_theory(t), reply_markup=_tview_kb(t))


@router.message(EditorStates.editing_t_checklist)
async def handle_tedit_checklist_input(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    raw = (message.text or "").strip()
    new_list: list[str] | None
    if raw == "-":
        new_list = []
    else:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            await message.answer("Не похоже на JSON. Пример: <code>[\"A\", \"B\"]</code>")
            return
        if not isinstance(parsed, list) or not all(isinstance(o, str) for o in parsed):
            await message.answer("Нужен массив строк.")
            return
        new_list = parsed
    data = await state.get_data()
    tid = data.get("edit_target_id")
    if not isinstance(tid, int):
        await state.clear()
        return
    async with session_factory() as db:
        await OpenQuestionRepository(db).update_fields(tid, checklist=new_list)
        await db.commit()
        t = await OpenQuestionRepository(db).get(tid)
    await state.clear()
    if t is None:
        return
    await message.answer(_format_theory(t), reply_markup=_tview_kb(t))


@router.message(EditorStates.editing_t_difficulty)
async def handle_tedit_difficulty_input(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    raw = (message.text or "").strip()
    try:
        value = int(raw)
    except ValueError:
        await message.answer("Нужно число от 1 до 5.")
        return
    if not 1 <= value <= 5:
        await message.answer("Только 1-5.")
        return
    data = await state.get_data()
    tid = data.get("edit_target_id")
    if not isinstance(tid, int):
        await state.clear()
        return
    async with session_factory() as db:
        await OpenQuestionRepository(db).update_fields(tid, difficulty=value)
        await db.commit()
        t = await OpenQuestionRepository(db).get(tid)
    await state.clear()
    if t is None:
        return
    await message.answer(_format_theory(t), reply_markup=_tview_kb(t))


@router.message(EditorStates.editing_t_code)
async def handle_tedit_code_input(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    raw = (message.text or "").rstrip("\n")
    new_value: str | None = None if raw.strip() == "-" else raw
    if new_value is not None and len(new_value) > 4096:
        await message.answer("Блок кода до 4096 символов.")
        return
    data = await state.get_data()
    tid = data.get("edit_target_id")
    if not isinstance(tid, int):
        await state.clear()
        return
    async with session_factory() as db:
        await OpenQuestionRepository(db).update_code(tid, code=new_value)
        await db.commit()
        t = await OpenQuestionRepository(db).get(tid)
    await state.clear()
    if t is None:
        return
    await message.answer(_format_theory(t), reply_markup=_tview_kb(t))


@router.message(EditorStates.editing_t_code_lang)
async def handle_tedit_code_lang_input(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    raw = (message.text or "").strip().lower()
    new_value: str | None
    if raw == "-" or not raw:
        new_value = None
    elif not re.fullmatch(r"[a-z0-9_+-]{1,32}", raw):
        await message.answer(
            "Язык должен быть короткой строкой (a-z, 0-9, _ + -). Например python, sql, js."
        )
        return
    else:
        new_value = raw
    data = await state.get_data()
    tid = data.get("edit_target_id")
    if not isinstance(tid, int):
        await state.clear()
        return
    async with session_factory() as db:
        await OpenQuestionRepository(db).update_code_language(tid, code_language=new_value)
        await db.commit()
        t = await OpenQuestionRepository(db).get(tid)
    await state.clear()
    if t is None:
        return
    await message.answer(_format_theory(t), reply_markup=_tview_kb(t))


def _parse_id_hint(query: str) -> int | None:
    raw = query.strip()
    if raw.startswith("#"):
        raw = raw[1:]
    if raw.isdigit():
        return int(raw)
    return None


def _search_prompt_kb(back_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data=back_cb)],
        ]
    )


@router.callback_query(F.data == "ape:qsearch:all")
async def handle_qsearch_all_start(
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
    await state.set_state(EditorStates.searching_q_all)
    await call.answer()
    await safe_edit_text(
        call.message,
        "<b>Поиск по всем тестовым вопросам</b>\n\n"
        "Пришли фрагмент текста (ищется по тексту, вариантам и пояснению) "
        "или <code>#1234</code> чтобы открыть вопрос по ID.",
        reply_markup=_search_prompt_kb("ape:cats"),
    )


@router.callback_query(F.data.startswith("ape:qsearch:cat:"))
async def handle_qsearch_cat_start(
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
    key = call.data.split(":", 3)[3]
    await state.set_state(EditorStates.searching_q_topic)
    await state.update_data(search_topic=key)
    await call.answer()
    await safe_edit_text(
        call.message,
        f"<b>Поиск в категории «{escape(display_name(key))}»</b>\n\n"
        "Пришли фрагмент текста или <code>#1234</code> для перехода по ID.",
        reply_markup=_search_prompt_kb(f"ape:cat:{key}"),
    )


@router.callback_query(F.data == "ape:tsearch:all")
async def handle_tsearch_all_start(
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
    await state.set_state(EditorStates.searching_t_all)
    await call.answer()
    await safe_edit_text(
        call.message,
        "<b>Поиск по всей теории</b>\n\n"
        "Пришли фрагмент текста или <code>#1234</code>.",
        reply_markup=_search_prompt_kb("ape:cats"),
    )


@router.callback_query(F.data.startswith("ape:tsearch:cat:"))
async def handle_tsearch_cat_start(
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
    key = call.data.split(":", 3)[3]
    await state.set_state(EditorStates.searching_t_topic)
    await state.update_data(search_topic=key)
    await call.answer()
    await safe_edit_text(
        call.message,
        f"<b>Поиск теории в категории «{escape(display_name(key))}»</b>\n\n"
        "Пришли фрагмент текста или <code>#1234</code>.",
        reply_markup=_search_prompt_kb(f"ape:cat:{key}"),
    )


def _qsearch_results_kb(
    items: list[Question], total: int, back_cb: str
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for q in items:
        marker = "🚫 " if not q.is_active else ""
        label = f"{marker}#{q.id} [{display_name(q.topic)}] {_short_preview(q.text)}"
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"ape:qview:{q.id}")]
        )
    rows.append([InlineKeyboardButton(text="🔍 Новый поиск", callback_data="ape:qsearch:all")])
    rows.append([InlineKeyboardButton(text="<< Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _tsearch_results_kb(
    items: list[OpenQuestion], total: int, back_cb: str
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for t in items:
        marker = "🚫 " if not t.is_active else ""
        label = f"{marker}#{t.id} [{display_name(t.topic)}] {_short_preview(t.text)}"
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"ape:tview:{t.id}")]
        )
    rows.append([InlineKeyboardButton(text="🔍 Новый поиск", callback_data="ape:tsearch:all")])
    rows.append([InlineKeyboardButton(text="<< Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _run_q_search(
    message: Message,
    session_factory: async_sessionmaker,
    state: FSMContext,
    query: str,
    topic: str | None,
    back_cb: str,
) -> None:
    qid = _parse_id_hint(query)
    if qid is not None:
        async with session_factory() as db:
            q = await QuestionRepository(db).get_by_id(qid)
        await state.clear()
        if q is None:
            await message.answer(
                f"Вопрос #{qid} не найден.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="<< Назад", callback_data=back_cb)]
                    ]
                ),
            )
            return
        await message.answer(_format_question(q), reply_markup=_qview_kb(q))
        return

    async with session_factory() as db:
        repo = QuestionRepository(db)
        items = await repo.search_admin(query, topic=topic, offset=0, limit=SEARCH_LIMIT)
        total = await repo.count_search_admin(query, topic=topic)
    await state.clear()
    if not items:
        await message.answer(
            f"По запросу <code>{escape(query)}</code> ничего не найдено.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔍 Новый поиск", callback_data="ape:qsearch:all")],
                    [InlineKeyboardButton(text="<< Назад", callback_data=back_cb)],
                ]
            ),
        )
        return
    header = (
        f"<b>Найдено: {total}</b>"
        + (f" (показано первых {SEARCH_LIMIT})" if total > SEARCH_LIMIT else "")
        + f"\nЗапрос: <code>{escape(query)}</code>"
        + (f"\nКатегория: {escape(display_name(topic))}" if topic else "")
    )
    await message.answer(header, reply_markup=_qsearch_results_kb(items, total, back_cb))


async def _run_t_search(
    message: Message,
    session_factory: async_sessionmaker,
    state: FSMContext,
    query: str,
    topic: str | None,
    back_cb: str,
) -> None:
    tid = _parse_id_hint(query)
    if tid is not None:
        async with session_factory() as db:
            t = await OpenQuestionRepository(db).get(tid)
        await state.clear()
        if t is None:
            await message.answer(
                f"Карточка #{tid} не найдена.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="<< Назад", callback_data=back_cb)]
                    ]
                ),
            )
            return
        await message.answer(_format_theory(t), reply_markup=_tview_kb(t))
        return

    async with session_factory() as db:
        repo = OpenQuestionRepository(db)
        items = await repo.search_admin(query, topic=topic, offset=0, limit=SEARCH_LIMIT)
        total = await repo.count_search_admin(query, topic=topic)
    await state.clear()
    if not items:
        await message.answer(
            f"По запросу <code>{escape(query)}</code> ничего не найдено.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔍 Новый поиск", callback_data="ape:tsearch:all")],
                    [InlineKeyboardButton(text="<< Назад", callback_data=back_cb)],
                ]
            ),
        )
        return
    header = (
        f"<b>Найдено: {total}</b>"
        + (f" (показано первых {SEARCH_LIMIT})" if total > SEARCH_LIMIT else "")
        + f"\nЗапрос: <code>{escape(query)}</code>"
        + (f"\nКатегория: {escape(display_name(topic))}" if topic else "")
    )
    await message.answer(header, reply_markup=_tsearch_results_kb(items, total, back_cb))


@router.message(EditorStates.searching_q_all)
async def handle_qsearch_all_input(
    message: Message,
    settings: Settings,
    session_factory: async_sessionmaker,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    query = (message.text or "").strip()
    if not query or len(query) < 2:
        await message.answer("Запрос слишком короткий, нужно минимум 2 символа.")
        return
    await _run_q_search(message, session_factory, state, query, None, "ape:cats")


@router.message(EditorStates.searching_q_topic)
async def handle_qsearch_topic_input(
    message: Message,
    settings: Settings,
    session_factory: async_sessionmaker,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    query = (message.text or "").strip()
    if not query or len(query) < 2:
        await message.answer("Запрос слишком короткий, нужно минимум 2 символа.")
        return
    data = await state.get_data()
    topic = data.get("search_topic")
    if not isinstance(topic, str):
        await state.clear()
        return
    await _run_q_search(message, session_factory, state, query, topic, f"ape:cat:{topic}")


@router.message(EditorStates.searching_t_all)
async def handle_tsearch_all_input(
    message: Message,
    settings: Settings,
    session_factory: async_sessionmaker,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    query = (message.text or "").strip()
    if not query or len(query) < 2:
        await message.answer("Запрос слишком короткий, нужно минимум 2 символа.")
        return
    await _run_t_search(message, session_factory, state, query, None, "ape:cats")


@router.message(EditorStates.searching_t_topic)
async def handle_tsearch_topic_input(
    message: Message,
    settings: Settings,
    session_factory: async_sessionmaker,
    state: FSMContext,
) -> None:
    if not _owner(message.from_user.id if message.from_user else None, settings):
        return
    query = (message.text or "").strip()
    if not query or len(query) < 2:
        await message.answer("Запрос слишком короткий, нужно минимум 2 символа.")
        return
    data = await state.get_data()
    topic = data.get("search_topic")
    if not isinstance(topic, str):
        await state.clear()
        return
    await _run_t_search(message, session_factory, state, query, topic, f"ape:cat:{topic}")
