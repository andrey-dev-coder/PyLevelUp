import json
import re
import uuid
from html import escape
from io import BytesIO

from aiogram import Bot, F, Router
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
    CATEGORIES,
    add_custom_category,
    all_category_keys,
    custom_categories,
    display_name,
    remove_custom_category,
)
from pylevelup.config import Settings
from pylevelup.repositories import (
    CustomCategoryRepository,
    OpenQuestionRepository,
    QuestionRepository,
    UserRepository,
)
from pylevelup.states.import_questions import ImportStates
from pylevelup.utils.edit import edit_or_send, safe_edit_text

router = Router(name="pylevelup_import")

KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,62}$")
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_QUESTIONS_PER_IMPORT = 500


def _is_owner(user_id: int | None, settings: Settings) -> bool:
    return user_id is not None and user_id == settings.owner_telegram_id


def _category_picker_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for cat in CATEGORIES:
        rows.append(
            [InlineKeyboardButton(text=cat.title, callback_data=f"imp:cat:{cat.key}")]
        )
    for cat in custom_categories():
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{cat.title} (своя)",
                    callback_data=f"imp:cat:{cat.key}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="➕ Создать новую категорию", callback_data="imp:new")]
    )
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="imp:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Импортировать", callback_data="imp:confirm"),
                InlineKeyboardButton(text="Отмена", callback_data="imp:cancel"),
            ]
        ]
    )


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data="imp:cancel")]
        ]
    )


def _categories_menu_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    customs = custom_categories()
    if not customs:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Пока нет пользовательских категорий",
                    callback_data="imp:noop",
                )
            ]
        )
    else:
        for cat in customs:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🗑 {cat.title}",
                        callback_data=f"impcat:del:{cat.key}",
                    )
                ]
            )
    rows.append(
        [InlineKeyboardButton(text="Закрыть", callback_data="imp:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Тестовые вопросы", callback_data="imp:type:test")],
            [InlineKeyboardButton(text="Теория (карточки с ответами)", callback_data="imp:type:theory")],
            [InlineKeyboardButton(text="Отмена", callback_data="imp:cancel")],
        ]
    )


FORMAT_HINT_TEST = (
    "<b>Формат файла (тесты)</b>\n"
    "Прикрепи .json (UTF-8) - массив объектов:\n"
    "<pre><code>[\n"
    "  {\n"
    "    \"text\": \"Что выведет print(0.1+0.2 == 0.3)?\",\n"
    "    \"options\": [\"True\", \"False\", \"Error\", \"None\"],\n"
    "    \"correct_index\": 1,\n"
    "    \"difficulty\": 1,\n"
    "    \"explanation\": \"Из-за бинарного представления 0.1+0.2 = 0.30000...4\"\n"
    "  }\n"
    "]</code></pre>\n"
    "Поля:\n"
    "- <b>text</b> (обязательно) - формулировка вопроса\n"
    "- <b>options</b> (обязательно, 2-6 шт) - варианты ответа\n"
    "- <b>correct_index</b> (обязательно) - индекс правильного варианта (0..len-1)\n"
    "- <b>difficulty</b> (1-5, по умолчанию 1)\n"
    "- <b>explanation</b> - пояснение, опционально\n"
    "- <b>external_key</b> - уникальный id, опционально (я сгенерирую если не указан)\n"
    "- <b>code</b> - блок кода под текстом вопроса (опционально). Отобразится в моноширинном виде с подсветкой если задан <b>code_language</b> (например python, sql, js).\n"
    f"Лимит на файл: {MAX_FILE_BYTES // 1024} КБ, до {MAX_QUESTIONS_PER_IMPORT} за раз."
)

FORMAT_HINT_THEORY = (
    "<b>Формат файла (теория / карточки)</b>\n"
    "Прикрепи .json (UTF-8) - массив объектов:\n"
    "<pre><code>[\n"
    "  {\n"
    "    \"text\": \"Что такое GIL в Python?\",\n"
    "    \"ideal_answer\": \"GIL (Global Interpreter Lock) - глобальная блокировка...\",\n"
    "    \"checklist\": [\"Упомянуть CPython\", \"Потоки vs процессы\"],\n"
    "    \"difficulty\": 2\n"
    "  }\n"
    "]</code></pre>\n"
    "Поля:\n"
    "- <b>text</b> (обязательно) - вопрос/тема карточки\n"
    "- <b>ideal_answer</b> (обязательно) - эталонный ответ\n"
    "- <b>checklist</b> - список пунктов чек-листа, опционально\n"
    "- <b>difficulty</b> (1-5, по умолчанию 2)\n"
    "- <b>external_key</b> - уникальный id, опционально\n"
    "- <b>code</b> / <b>code_language</b> - блок кода с подсветкой, опционально\n"
    f"Лимит на файл: {MAX_FILE_BYTES // 1024} КБ, до {MAX_QUESTIONS_PER_IMPORT} за раз."
)


@router.message(Command("import"))
async def handle_import_cmd(message: Message, state: FSMContext, settings: Settings) -> None:
    if not _is_owner(message.from_user.id if message.from_user else None, settings):
        return
    await state.clear()
    await state.set_state(ImportStates.choosing_category)
    await message.answer(
        "<b>Импорт вопросов</b>\n\nВыбери категорию или создай новую:",
        reply_markup=_category_picker_keyboard(),
    )


@router.message(Command("categories"))
async def handle_categories_cmd(message: Message, settings: Settings) -> None:
    if not _is_owner(message.from_user.id if message.from_user else None, settings):
        return
    await message.answer(
        "<b>Пользовательские категории</b>\n\nНажми на категорию чтобы удалить её. Вопросы при этом останутся в базе.",
        reply_markup=_categories_menu_keyboard(),
    )


@router.callback_query(F.data == "imp:cancel")
async def handle_cancel(call: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if not _is_owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    await state.clear()
    await call.answer("Отменено")
    if call.message is not None:
        await safe_edit_text(call.message, "Импорт отменён.")


@router.callback_query(F.data == "imp:noop")
async def handle_noop(call: CallbackQuery) -> None:
    await call.answer()


@router.callback_query(F.data.startswith("impcat:del:"))
async def handle_delete_custom_category(
    call: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.data is None:
        await call.answer()
        return
    key = call.data.split(":", 2)[2]
    async with session_factory() as db:
        repo = CustomCategoryRepository(db)
        removed = await repo.delete(key)
        await db.commit()
    if removed:
        remove_custom_category(key)
        await call.answer("Удалена")
    else:
        await call.answer("Не найдена")
    if call.message is not None:
        await safe_edit_text(
            call.message,
            "<b>Пользовательские категории</b>\n\nНажми на категорию чтобы удалить её.",
            reply_markup=_categories_menu_keyboard(),
        )


@router.callback_query(F.data.startswith("imp:cat:"))
async def handle_pick_category(
    call: CallbackQuery,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not _is_owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    key = call.data.split(":", 2)[2]
    if key not in all_category_keys():
        await call.answer("Категория не найдена")
        return
    await state.update_data(import_topic=key)
    await state.set_state(ImportStates.choosing_type)
    await call.answer()
    await safe_edit_text(
        call.message,
        f"<b>Категория:</b> {escape(display_name(key))}\n\nЧто импортируем?",
        reply_markup=_type_keyboard(),
    )


@router.callback_query(F.data.startswith("imp:type:"))
async def handle_pick_type(
    call: CallbackQuery,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not _is_owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.data is None or call.message is None:
        await call.answer()
        return
    import_type = call.data.split(":", 2)[2]
    if import_type not in ("test", "theory"):
        await call.answer()
        return
    data = await state.get_data()
    topic = data.get("import_topic")
    if not isinstance(topic, str):
        await state.clear()
        await call.answer("Сессия сброшена")
        return
    await state.update_data(import_type=import_type)
    await state.set_state(ImportStates.awaiting_file)
    await call.answer()
    hint = FORMAT_HINT_TEST if import_type == "test" else FORMAT_HINT_THEORY
    await safe_edit_text(
        call.message,
        f"<b>Категория:</b> {escape(display_name(topic))}\n\n{hint}",
        reply_markup=_cancel_keyboard(),
    )


@router.callback_query(F.data == "imp:new")
async def handle_new_category(
    call: CallbackQuery,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not _is_owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.message is None:
        await call.answer()
        return
    await state.set_state(ImportStates.creating_category_key)
    await call.answer()
    await safe_edit_text(
        call.message,
        "<b>Новая категория</b>\n\n"
        "Пришли <b>ключ</b> категории - latin, цифры и подчёркивания, 2-63 символа. "
        "Это идентификатор для базы.\nПример: <code>redis_streams</code>, <code>graphql</code>",
        reply_markup=_cancel_keyboard(),
    )


@router.message(ImportStates.creating_category_key)
async def handle_category_key(
    message: Message,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not _is_owner(message.from_user.id if message.from_user else None, settings):
        return
    if message.text is None:
        await message.answer("Жду текст. Пришли ключ категории.")
        return
    raw = message.text.strip().lower()
    if not KEY_RE.match(raw):
        await message.answer(
            "Неверный формат ключа. Можно только latin-буквы, цифры и подчёркивания, длина 2-63.",
            reply_markup=_cancel_keyboard(),
        )
        return
    if raw in all_category_keys():
        await message.answer(
            f"Категория <code>{escape(raw)}</code> уже существует. Используй её через /import.",
            reply_markup=_cancel_keyboard(),
        )
        return
    await state.update_data(new_category_key=raw)
    await state.set_state(ImportStates.creating_category_title)
    await message.answer(
        f"Ключ: <code>{escape(raw)}</code>\n\n"
        "Теперь пришли <b>читаемое название</b> - то, что будет показываться в кнопках и профиле. "
        "Например: <code>Redis Streams</code>",
        reply_markup=_cancel_keyboard(),
    )


@router.message(ImportStates.creating_category_title)
async def handle_category_title(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_owner(message.from_user.id if message.from_user else None, settings):
        return
    if message.text is None:
        await message.answer("Жду текст. Пришли название категории.")
        return
    title = message.text.strip()
    if len(title) < 2 or len(title) > 128:
        await message.answer("Название от 2 до 128 символов.", reply_markup=_cancel_keyboard())
        return
    data = await state.get_data()
    key = data.get("new_category_key")
    if not isinstance(key, str):
        await state.clear()
        await message.answer("Сессия сброшена, начни заново через /import.")
        return
    user_id_for_repo: int | None = None
    async with session_factory() as db:
        user_repo = UserRepository(db)
        if message.from_user is not None:
            existing = await user_repo.get_by_telegram_id(message.from_user.id)
            if existing is not None:
                user_id_for_repo = existing.id
        repo = CustomCategoryRepository(db)
        await repo.upsert(
            key=key,
            title=title,
            short=title[:32],
            created_by_user_id=user_id_for_repo,
        )
        await db.commit()
    add_custom_category(key, title, title[:32])
    await state.update_data(import_topic=key)
    await state.set_state(ImportStates.choosing_type)
    await message.answer(
        f"Категория создана: <b>{escape(title)}</b> (<code>{escape(key)}</code>)\n\n"
        "Что импортируем?",
        reply_markup=_type_keyboard(),
    )


@router.message(ImportStates.awaiting_file, F.document)
async def handle_file(
    message: Message,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
) -> None:
    if not _is_owner(message.from_user.id if message.from_user else None, settings):
        return
    if message.document is None:
        return
    if (message.document.file_size or 0) > MAX_FILE_BYTES:
        await message.answer(
            f"Файл слишком большой. Лимит {MAX_FILE_BYTES // 1024} КБ.",
            reply_markup=_cancel_keyboard(),
        )
        return
    name = (message.document.file_name or "").lower()
    if not name.endswith(".json"):
        await message.answer(
            "Жду файл с расширением .json.",
            reply_markup=_cancel_keyboard(),
        )
        return
    buf = BytesIO()
    try:
        await bot.download(message.document, destination=buf)
    except Exception as exc:
        await message.answer(
            f"Не смог скачать файл: {escape(str(exc))}",
            reply_markup=_cancel_keyboard(),
        )
        return
    raw_bytes = buf.getvalue()
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        await message.answer(
            "Файл не в UTF-8. Сохрани как UTF-8 и пришли снова.",
            reply_markup=_cancel_keyboard(),
        )
        return
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        await message.answer(
            f"JSON невалидный: {escape(str(exc))}",
            reply_markup=_cancel_keyboard(),
        )
        return
    if not isinstance(payload, list):
        await message.answer(
            "Ожидаю массив объектов на верхнем уровне (<code>[ {...}, {...} ]</code>).",
            reply_markup=_cancel_keyboard(),
        )
        return
    data = await state.get_data()
    topic = data.get("import_topic")
    import_type = data.get("import_type", "test")
    if not isinstance(topic, str):
        await state.clear()
        await message.answer("Сессия сброшена, начни заново через /import.")
        return
    if import_type == "theory":
        valid, errors = _validate_theory_payload(payload, topic)
    else:
        valid, errors = _validate_payload(payload, topic)
    if not valid and errors:
        sample = "\n".join(errors[:10])
        more = f"\n... ещё {len(errors) - 10} ошибок" if len(errors) > 10 else ""
        item_name = "карточек" if import_type == "theory" else "вопросов"
        await message.answer(
            f"В файле нет валидных {item_name}. Первые ошибки:\n<pre>{escape(sample)}{escape(more)}</pre>",
            reply_markup=_cancel_keyboard(),
        )
        return
    await state.update_data(import_valid=valid, import_errors=errors[:20])
    await state.set_state(ImportStates.confirming)
    item_name = "карточек" if import_type == "theory" else "вопросов"
    preview_lines = [
        f"<b>Готово к импорту:</b> {len(valid)} {item_name}",
        f"<b>Категория:</b> {escape(display_name(topic))}",
        f"<b>Тип:</b> {'Теория' if import_type == 'theory' else 'Тесты'}",
    ]
    if errors:
        preview_lines.append(f"<b>Невалидных:</b> {len(errors)}")
        head = "\n".join(errors[:5])
        preview_lines.append(f"Первые ошибки:\n<pre>{escape(head)}</pre>")
    if valid:
        sample_q = valid[0]
        preview_lines.append("<b>Пример:</b>")
        preview_lines.append(f"<i>{escape(sample_q['text'][:200])}</i>")
    await message.answer(
        "\n".join(preview_lines),
        reply_markup=_confirm_keyboard(),
    )


@router.message(ImportStates.awaiting_file)
async def handle_awaiting_file_other(
    message: Message,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not _is_owner(message.from_user.id if message.from_user else None, settings):
        return
    await message.answer(
        "Жду JSON-файл. Прикрепи документ или нажми Отмена.",
        reply_markup=_cancel_keyboard(),
    )


@router.callback_query(F.data == "imp:confirm")
async def handle_confirm(
    call: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if not _is_owner(call.from_user.id if call.from_user else None, settings):
        await call.answer()
        return
    if call.message is None:
        await call.answer()
        return
    data = await state.get_data()
    valid = data.get("import_valid") or []
    topic = data.get("import_topic")
    import_type = data.get("import_type", "test")
    if not isinstance(valid, list) or not isinstance(topic, str) or not valid:
        await call.answer("Нет данных")
        await state.clear()
        return
    await call.answer("Импортирую...")
    inserted = 0
    failed = 0
    if import_type == "theory":
        async with session_factory() as db:
            repo = OpenQuestionRepository(db)
            for item in valid:
                try:
                    await repo.upsert(
                        external_key=item["external_key"],
                        topic=topic,
                        difficulty=int(item.get("difficulty", 2)),
                        text=item["text"],
                        ideal_answer=item["ideal_answer"],
                        checklist=item.get("checklist"),
                        code=item.get("code"),
                        code_language=item.get("code_language"),
                    )
                    inserted += 1
                except Exception:
                    failed += 1
            await db.commit()
    else:
        async with session_factory() as db:
            repo = QuestionRepository(db)
            for item in valid:
                try:
                    await repo.upsert_external(
                        external_key=item["external_key"],
                        topic=topic,
                        difficulty=int(item.get("difficulty", 1)),
                        text=item["text"],
                        options=list(item["options"]),
                        correct_index=int(item["correct_index"]),
                        explanation=item.get("explanation"),
                        code=item.get("code"),
                        code_language=item.get("code_language"),
                    )
                    inserted += 1
                except Exception:
                    failed += 1
            await db.commit()
    await state.clear()
    type_label = "Теория" if import_type == "theory" else "Тесты"
    await edit_or_send(
        call,
        f"<b>Импорт завершён</b>\nТип: {type_label}\nКатегория: {escape(display_name(topic))}\n"
        f"Добавлено / обновлено: {inserted}\n"
        f"Ошибок: {failed}",
    )


def _validate_payload(payload: list, topic: str) -> tuple[list[dict], list[str]]:
    valid: list[dict] = []
    errors: list[str] = []
    seen_keys: set[str] = set()
    if len(payload) > MAX_QUESTIONS_PER_IMPORT:
        errors.append(
            f"[файл] лимит {MAX_QUESTIONS_PER_IMPORT}, обработаю первые {MAX_QUESTIONS_PER_IMPORT}"
        )
        payload = payload[:MAX_QUESTIONS_PER_IMPORT]
    for idx, raw in enumerate(payload):
        if not isinstance(raw, dict):
            errors.append(f"#{idx}: не объект")
            continue
        text = raw.get("text")
        if not isinstance(text, str) or len(text.strip()) < 3:
            errors.append(f"#{idx}: пустой или короткий text")
            continue
        opts = raw.get("options")
        if not isinstance(opts, list) or len(opts) < 2 or len(opts) > 6:
            errors.append(f"#{idx}: options должен быть списком из 2-6 строк")
            continue
        if any(not isinstance(o, str) or not o.strip() for o in opts):
            errors.append(f"#{idx}: пустой вариант ответа")
            continue
        try:
            correct = int(raw.get("correct_index"))
        except (TypeError, ValueError):
            errors.append(f"#{idx}: correct_index не число")
            continue
        if correct < 0 or correct >= len(opts):
            errors.append(f"#{idx}: correct_index вне диапазона")
            continue
        try:
            difficulty = int(raw.get("difficulty", 1))
        except (TypeError, ValueError):
            difficulty = 1
        if difficulty < 1 or difficulty > 5:
            difficulty = max(1, min(5, difficulty))
        explanation = raw.get("explanation")
        if explanation is not None and not isinstance(explanation, str):
            explanation = None
        external_key = raw.get("external_key")
        if not isinstance(external_key, str) or not external_key.strip():
            external_key = f"import_{topic}_{uuid.uuid4().hex[:12]}"
        external_key = external_key.strip()
        if external_key in seen_keys:
            errors.append(f"#{idx}: дублирующийся external_key {external_key}")
            continue
        seen_keys.add(external_key)
        code_value = raw.get("code")
        if not isinstance(code_value, str) or not code_value.strip():
            code_value = None
        else:
            code_value = code_value.rstrip("\n")
        code_language = raw.get("code_language") or raw.get("language")
        if not isinstance(code_language, str) or not code_language.strip():
            code_language = None
        else:
            code_language = code_language.strip().lower()[:32]
        valid.append(
            {
                "external_key": external_key,
                "text": text.strip(),
                "options": [o.strip() for o in opts],
                "correct_index": correct,
                "difficulty": difficulty,
                "explanation": explanation.strip() if isinstance(explanation, str) else None,
                "code": code_value,
                "code_language": code_language,
            }
        )
    return valid, errors


def _validate_theory_payload(payload: list, topic: str) -> tuple[list[dict], list[str]]:
    valid: list[dict] = []
    errors: list[str] = []
    seen_keys: set[str] = set()
    if len(payload) > MAX_QUESTIONS_PER_IMPORT:
        errors.append(
            f"[файл] лимит {MAX_QUESTIONS_PER_IMPORT}, обработаю первые {MAX_QUESTIONS_PER_IMPORT}"
        )
        payload = payload[:MAX_QUESTIONS_PER_IMPORT]
    for idx, raw in enumerate(payload):
        if not isinstance(raw, dict):
            errors.append(f"#{idx}: не объект")
            continue
        text = raw.get("text")
        if not isinstance(text, str) or len(text.strip()) < 3:
            errors.append(f"#{idx}: пустой или короткий text")
            continue
        ideal_answer = raw.get("ideal_answer")
        if not isinstance(ideal_answer, str) or len(ideal_answer.strip()) < 3:
            errors.append(f"#{idx}: пустой или короткий ideal_answer")
            continue
        checklist = raw.get("checklist")
        if checklist is not None:
            if not isinstance(checklist, list):
                checklist = None
            else:
                checklist = [str(c) for c in checklist if isinstance(c, str) and c.strip()]
                if not checklist:
                    checklist = None
        try:
            difficulty = int(raw.get("difficulty", 2))
        except (TypeError, ValueError):
            difficulty = 2
        if difficulty < 1 or difficulty > 5:
            difficulty = max(1, min(5, difficulty))
        external_key = raw.get("external_key")
        if not isinstance(external_key, str) or not external_key.strip():
            external_key = f"theory_{topic}_{uuid.uuid4().hex[:12]}"
        external_key = external_key.strip()
        if external_key in seen_keys:
            errors.append(f"#{idx}: дублирующийся external_key {external_key}")
            continue
        seen_keys.add(external_key)
        code_value = raw.get("code")
        if not isinstance(code_value, str) or not code_value.strip():
            code_value = None
        else:
            code_value = code_value.rstrip("\n")
        code_language = raw.get("code_language") or raw.get("language")
        if not isinstance(code_language, str) or not code_language.strip():
            code_language = None
        else:
            code_language = code_language.strip().lower()[:32]
        valid.append(
            {
                "external_key": external_key,
                "text": text.strip(),
                "ideal_answer": ideal_answer.strip(),
                "checklist": checklist,
                "difficulty": difficulty,
                "code": code_value,
                "code_language": code_language,
            }
        )
    return valid, errors
