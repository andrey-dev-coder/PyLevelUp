# Developer Guide

Этот документ - полная инструкция для нового разработчика, который пришёл в
репозиторий и хочет понять: что где лежит, какие паттерны используются, как
безопасно добавить новую фичу, как тестировать локально, какие подводные камни
ждут в проде.

## Содержание

1. [Стек и идеология](#1-стек-и-идеология)
2. [Структура репозитория, файл за файлом](#2-структура-репозитория-файл-за-файлом)
3. [Конфигурация и переменные окружения](#3-конфигурация-и-переменные-окружения)
4. [База данных: модели, миграции, индексы](#4-база-данных-модели-миграции-индексы)
5. [Репозитории: паттерн доступа к данным](#5-репозитории-паттерн-доступа-к-данным)
6. [Сервисы: бизнес-логика](#6-сервисы-бизнес-логика)
7. [Handlers и routers aiogram](#7-handlers-и-routers-aiogram)
8. [FSM-состояния](#8-fsm-состояния)
9. [Middleware: пользователь и доступ](#9-middleware-пользователь-и-доступ)
10. [Кэш сессии и Redis](#10-кэш-сессии-и-redis)
11. [Алгоритм Spaced Repetition](#11-алгоритм-spaced-repetition)
12. [Categories: builtin + custom](#12-categories-builtin--custom)
13. [Access codes и whitelist тем](#13-access-codes-и-whitelist-тем)
14. [Учебные планы (learning paths)](#14-учебные-планы-learning-paths)
15. [Импорт контента из JSON](#15-импорт-контента-из-json)
16. [Celery: фоновые задачи и beat](#16-celery-фоновые-задачи-и-beat)
17. [Как добавить новую фичу](#17-как-добавить-новую-фичу)
18. [Локальная разработка и тестирование](#18-локальная-разработка-и-тестирование)
19. [Стиль кода и инварианты](#19-стиль-кода-и-инварианты)

## 1. Стек и идеология

- **aiogram 3.x** в режиме long polling. Никакого webhook'а - проще всего
  деплоить, не нужно держать HTTPS.
- **SQLAlchemy 2.0 async + Alembic.** Только асинхронный engine.
- **PostgreSQL 16** как основная БД. `JSONB` используется для гетерогенных
  списков (варианты ответа, чек-лист, allowed_topics).
- **Redis 7** для FSM-storage и для буферизации активной тест-сессии. Это
  снимает 90% нагрузки с PostgreSQL: на ответ юзера БД не дёргается.
- **Celery 5** с Redis-брокером. Beat запускается отдельным процессом
  (Procfile). Задачи: рассылки, пересчёт рейтинга, проверки ачивок.
- **structlog** для структурированных логов.

Идеология слоистая: тонкие routers → сервисы (логика) → репозитории (SQL) →
модели. Прямых запросов из routers в БД мы стараемся не делать - всё идёт
через репозитории.

## 2. Структура репозитория, файл за файлом

### Корень

| Файл | Назначение |
| --- | --- |
| `pyproject.toml` | зависимости + ruff конфиг |
| `Dockerfile`, `docker-compose.yml` | локальный запуск со всеми сервисами |
| `Procfile` | команды для Railway: `web` (бот), `worker`, `beat` |
| `alembic.ini` | конфиг Alembic |
| `.env.example` | список переменных окружения |

### `pylevelup/`

| Модуль | Что внутри |
| --- | --- |
| `config.py` | `Settings` (pydantic-settings) - типобезопасная загрузка `.env` |
| `bot.py` | создание `Bot`, `Dispatcher`, регистрация роутеров, команд `/`-меню |
| `__main__.py` | `python -m pylevelup` - точка входа для polling |
| `celery_app.py` | Celery + beat schedule |
| `categories.py` | реестр встроенных тем + кэш кастомных |
| `logger.py` | structlog setup |

### `db/`

| Файл | Назначение |
| --- | --- |
| `base.py` | `DeclarativeBase`, единая naming-convention для FK/индексов |
| `session.py` | async engine, sessionmaker, dependency factory |
| `models.py` | все ORM-модели в одном файле (User, Question, OpenQuestion, Attempt, UserProgress, DailySession, Bookmark, MockSession, UserAchievement, AccessCode, UserTopicAccess, LearningPath, LearningPathStep, UserLearningPathProgress, CustomCategory, BotSettings и др.) |

### `repositories/`

Тонкий слой над `AsyncSession`. Один файл = один аггрегат. Все методы
асинхронные. Транзакции открываются *вне* репозиториев - чаще всего в handler-е
через `async with session_factory() as db:` + `await db.commit()`.

Текущий список см. в [README.md](README.md#структура-репозитория).

### `services/`

Логика, которая не сводится к одному CRUD-вызову.

| Файл | Что делает |
| --- | --- |
| `spaced_repetition.py` | чистая функция SuperMemo-2 (без БД) |
| `session_cache.py` | работа с Redis: создать сессию, прочитать состояние, добавить ответ, flush |
| `test_session_service.py` | оркестратор `/test`: старт, выдача вопроса, обработка ответа, завершение |
| `stats_service.py` | агрегации с оконными функциями (rank, percentile) |
| `ranking_service.py` | пересчёт `users.ranking_score` |
| `broadcast.py` | пакетная отправка с обработкой `Forbidden`/`Retry-After` |
| `topic_access.py` | бизнес-правила whitelist тем |
| `mastery.py` | расчёт уверенности по теме (точность × объём) |
| `study_service.py` | режим карточек теории |
| `achievement_evaluator.py`, `achievement_notify.py`, `achievements.py` | ачивки |

### `handlers/`

aiogram routers, по одному файлу на фичу. Каждый файл объявляет свой `router =
Router(name="...")`. Все routers подключаются в `pylevelup/handlers/__init__.py`
через `build_root_router()`.

### `middlewares/`

| Файл | Что делает |
| --- | --- |
| `user.py` | upsert юзера в БД на каждом апдейте; кладёт `User`, `UserRepository`, `session_factory` в `data` (DI) |
| `access.py` | проверяет авторизацию, бан, whitelist категорий; блокирует чужие callback-кнопки |

### `states/`

`StatesGroup`-ы для FSM. По одному файлу на крупную фичу
(`test.py`, `mock.py`, `import_questions.py`, `report.py`, `search.py`, `ai.py`).

### `keyboards/`

Общие билдеры клавиатур (`inline.py`). Локальные клавиатуры
обычно живут прямо в handler-е, если используются только там.

### `tasks/`

Celery-задачи: `reminders.py` (ежедневная рассылка), `ranking.py` (пересчёт
рейтинга), `achievements.py` (фоновая проверка ачивок).

### `utils/`

`edit.py` - `safe_edit_text()` и `edit_or_send()`, которые подавляют
`MessageNotModified` и фоллбекят на новое сообщение при ошибках Telegram API.

## 3. Конфигурация и переменные окружения

Все переменные читаются через `Settings` (см. `pylevelup/config.py`). Список -
в `.env.example`. Ключевые:

| Переменная | Описание |
| --- | --- |
| `BOT_TOKEN` | токен от BotFather, обязательно |
| `OWNER_TELEGRAM_ID` | Telegram ID владельца. Только он видит админ-команды |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `REDIS_URL` | `redis://host:6379/0` |
| `CELERY_BROKER_URL` | обычно тот же Redis с другим db (`/1`) |
| `ACCESS_CODE` | глобальный код полного доступа (опционально) |
| `DAILY_REMINDER_HOUR_UTC` | час рассылки напоминаний (0-23) |
| `RANKING_REFRESH_MINUTES` | интервал пересчёта рейтинга |
| `SESSION_TIMEOUT_SECONDS` | TTL активной сессии в Redis |

Если переменная не определена и не имеет дефолта - бот упадёт при старте.

## 4. База данных: модели, миграции, индексы

### Кардинальные модели

- **`users`** - учётка Telegram. Поля: `telegram_id` (uniq, индекс),
  `is_authorized`, `is_banned`, `is_active`, `current_streak`, `max_streak`,
  `total_correct`, `total_answered`, `ranking_score`, `last_ranking_position`,
  `reminders_enabled`, `reminders_paused_until`, `timezone`, `hints_used_today`,
  `hints_reset_date`.
- **`questions`** - тестовый вопрос (с вариантами). Поля: `topic`,
  `difficulty`, `text`, `options` (JSONB), `correct_index`, `explanation`,
  `external_key` (uniq), `is_active`.
- **`open_questions`** - теория (карточки). Поля: `topic`, `difficulty`,
  `text`, `ideal_answer`, `checklist` (JSONB), `external_key` (uniq),
  `is_active`.
- **`user_progress`** - состояние SR-алгоритма per (user, question):
  `ease_factor`, `interval_days`, `repetitions`, `next_review_at`,
  `last_quality`.
- **`attempts`** - журнал ответов. Каждый ответ = одна строка.
- **`daily_sessions`** - агрегаты дневной сессии.
- **`daily_challenges`** - челлендж дня (выбор вопросов на сегодня).
- **`bookmarks`**, **`reports`**, **`mock_sessions`**, **`user_achievements`**.
- **`access_codes`** - кодовые слова: `code` (uniq), `label`, `allowed_topics`
  (JSONB list).
- **`user_topic_access`** - whitelist тем для конкретного юзера. Композитный
  PK (`user_id`, `topic_key`). Пустой список = все темы.
- **`learning_paths`**, **`learning_path_steps`**, **`user_learning_path_progress`**.
- **`custom_categories`** - кастомные темы (key, title, short).
- **`bot_settings`** - key-value таблица для глобальных настроек (текущий код
  доступа, всякое).

### Каскады

ВСЕ FK от `users.id` объявлены с `ondelete="CASCADE"` (кроме одного `SET NULL`
для жалоб - там автор может стать `NULL`, сама жалоба остаётся). Это значит:
удаление юзера через `UserRepository.delete_user()` снесёт за собой все его
данные, не нужно вручную чистить попытки/прогресс/закладки.

### Миграции

Все Alembic-миграции в `migrations/versions/`. Имена осмысленные:
`b0c1d2e3f4aa_learning_paths.py`, `af1b2c3d4e55_access_codes.py` и т.д.

Создать новую:

```bash
alembic revision --autogenerate -m "add my_new_table"
# Проверить файл - autogenerate ловит не всё, проверь руками!
alembic upgrade head
```

Откатить на одну версию:

```bash
alembic downgrade -1
```

Перейти на конкретную:

```bash
alembic upgrade <revision_id>
```

В CI/CD Railway автоматически применяет `alembic upgrade head` через release
phase (см. `Procfile`).

## 5. Репозитории: паттерн доступа к данным

Стандартный шаблон:

```python
class FooRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, foo_id: int) -> Foo | None:
        return await self.session.get(Foo, foo_id)

    async def list_active(self, limit: int = 10) -> list[Foo]:
        stmt = select(Foo).where(Foo.is_active.is_(True)).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())
```

Правила:

- Никогда не вызываем `self.session.commit()` в репозитории. Это делается
  снаружи (в handler-е), чтобы транзакция охватывала логически связанные
  операции.
- Используем `await self.session.flush()` если нужно получить id новой
  строки до коммита.
- `pg_insert(...).on_conflict_do_update(...)` для upsert-ов по
  `external_key`.

## 6. Сервисы: бизнес-логика

Сервис принимает `session_factory` (или прямую `AsyncSession`) и оперирует
репозиториями. Сервис не знает про aiogram, его можно дёрнуть из Celery-задачи
или из CLI.

Пример хорошего сервиса - `TestSessionService`: он принимает решения «выдать
следующий вопрос», «когда делать flush», но в нём нет ни Telegram, ни
клавиатур, ни форматирования сообщений.

## 7. Handlers и routers aiogram

Структура файла handler-а:

```python
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.config import Settings
from pylevelup.repositories import FooRepository
from pylevelup.utils.edit import safe_edit_text

router = Router(name="pylevelup_foo")


@router.message(Command("foo"))
async def handle_foo_cmd(
    message: Message,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    async with session_factory() as db:
        repo = FooRepository(db)
        items = await repo.list_active()
    await message.answer(f"Found {len(items)} items")
```

Dependency Injection: все параметры handler-а после стандартных aiogram-овых
(`Message`/`CallbackQuery`, `Command`/`CommandObject`, `FSMContext`, `Bot`,
`State`) резолвятся из `dp.workflow_data`. Туда мы кладём `session_factory`,
`settings`, и т.д. в `bot.py`.

### Конвенции callback_data

- `ap:*` - корневая админ-панель (`/panel`).
- `ape:*` - админ-редактор вопросов.
- `app:*` - админ-учебные планы.
- `ut:*` - command `/user_topics`.
- `bm:*` - закладки.
- `ans:*` - ответ на вопрос в тренажёре.
- ...

Постарайтесь держать callback_data в пределах 64 байт - это лимит Telegram.

### Утилиты редактирования

В `pylevelup/utils/edit.py`:

- `safe_edit_text(message, text, reply_markup=None)` - редактирует сообщение,
  глушит `TelegramBadRequest: message is not modified`, при ошибке шлёт новое
  сообщение.
- `edit_or_send(call, ...)` - комбо: пробует отредактировать, иначе шлёт новое.

Используйте их вместо `message.edit_text()` напрямую - иначе словите
unhandled-exception при повторной отправке того же содержимого.

## 8. FSM-состояния

aiogram FSM с Redis-storage. На каждый сценарий многошагового ввода - свой
`StatesGroup`.

Хранилище: `RedisStorage` (см. `bot.py`). Состояние юзера хранится в Redis
под ключом `fsm:default:<chat_id>:<user_id>:state`, данные - `...:data`.

Пример (редактор вопросов):

```python
class EditorStates(StatesGroup):
    editing_q_text = State()
    searching_q_topic = State()


@router.callback_query(F.data.startswith("ape:qe:"))
async def start_edit(call, state: FSMContext):
    await state.set_state(EditorStates.editing_q_text)
    await state.update_data(question_id=42)
    await call.answer()


@router.message(EditorStates.editing_q_text)
async def receive_edit(message, state: FSMContext):
    data = await state.get_data()
    qid = data["question_id"]
    new_text = message.text
    ...
    await state.clear()
```

Важно: после успешного ввода вызывайте `state.clear()`. Иначе следующий
случайный текст юзера снова попадёт в этот handler.

## 9. Middleware: пользователь и доступ

### `middlewares/user.py`

На каждом апдейте выполняет upsert юзера в БД и кладёт `User` объект в
`data["user"]`. Также кладёт `session_factory` и `UserRepository(session)`.

### `middlewares/access.py`

Перед тем как пустить апдейт в handler:

1. Если юзер забанен (`is_banned=True`) - молча игнорирует (или отвечает
   alert для callback-ов).
2. Если юзер не авторизован (`is_authorized=False`) и не в команде `/start` -
   просит ввести код доступа.
3. Если юзер тыкает callback-кнопку, которая привязана к категории не из его
   whitelist - alert «эта тема тебе не открыта».

Owner (`OWNER_TELEGRAM_ID`) обходит всё это.

## 10. Кэш сессии и Redis

См. подробности в [ARCHITECTURE.md §4](ARCHITECTURE.md#4-кэш-и-снижение-нагрузки-на-бд).
Ключ в Redis: `test_session:<user_id>`. Hash содержит: `category`,
`question_ids` (JSON list), `current_index`, `correct_count`,
`pending_attempts` (JSON list), `started_at`, `finished` (bool).

TTL по умолчанию = `SESSION_TIMEOUT_SECONDS` (3600 сек). Flush в БД делается
при:

- завершении сессии (юзер нажал «Завершить» или ответил на все);
- ручном flush из админа (на будущее);
- истечении TTL (фоновый воркер периодически сканирует и докомитит).

## 11. Алгоритм Spaced Repetition

Полный псевдокод см. [ARCHITECTURE.md §5](ARCHITECTURE.md#5-алгоритм-spaced-repetition).
Чистая функция `evaluate(prev_state, quality) -> next_state` живёт в
`services/spaced_repetition.py` и легко юнит-тестится без БД.

## 12. Categories: builtin + custom

- **Builtin** - 14 жёстко прошитых тем в `pylevelup/categories.py` (Python,
  SQL, async, и т.д.). Доступ через `CATEGORIES` и `CATEGORY_BY_KEY`.
- **Custom** - юзер-определённые через `/categories` или импортом нового
  `topic`. Хранятся в `custom_categories`. Загружаются в кэш через
  `custom_categories()` при старте бота и пересинхронизируются после
  CRUD-операций.
- `display_name(key)` - человекочитаемое имя для любой категории (builtin или
  custom).
- `all_category_keys()` - объединение builtin + custom.

## 13. Access codes и whitelist тем

Два пересекающихся механизма:

1. **Access codes** (`access_codes`) - кодовые слова. Каждый код имеет
   `allowed_topics` (JSONB list). Когда юзер вводит код, мы:
   - помечаем его `is_authorized=True`,
   - копируем `allowed_topics` в его `user_topic_access` (если непустой) -
     это становится его whitelist'ом.
   - Если `allowed_topics` пустой (или код - глобальный `ACCESS_CODE`),
     whitelist остаётся пустым = доступ ко всему.

2. **User topic access** (`user_topic_access`) - индивидуальный whitelist
   уже после авторизации. Админ может в `/panel` тыкнуть «📂 Темы доступа»
   и галочками отметить, что юзеру доступно.

Логика whitelist: **пустой список = все темы**. Это сделано чтобы существующие
юзеры (без записей) сохранили дефолтный «всё открыто» поведение.

`TopicAccessRepository` и `services/topic_access.py` инкапсулируют это.

## 14. Учебные планы (learning paths)

3 таблицы:

- `learning_paths` - сам план: `slug`, `title`, `description`, `is_active`.
- `learning_path_steps` - блок плана: `path_id`, `order_index`, `topic_key`,
  `title`, `min_questions`, `required_accuracy`.
- `user_learning_path_progress` - прогресс юзера по плану: `path_id`,
  `user_id`, `started_at`, `completed_at`.

Прогресс блока считается на лету через `attempts` JOIN `questions WHERE topic =
step.topic`. Когда юзер ответил `>= min_questions` И его точность `>=
required_accuracy`, блок считается пройденным. Следующий блок открывается
автоматически.

### Хэндлеры

- Юзер: `handlers/learning_paths.py` (`/paths`).
- Админ: `handlers/admin_paths.py` (CRUD планов и блоков через `app:*`
  callback-prefix).

## 15. Импорт контента из JSON

Хэндлер `handlers/import_questions.py`, команда `/import`. FSM-сценарий:

1. Юзер выбирает категорию (или создаёт новую через `/categories`).
2. Выбирает тип: «тестовые вопросы» или «теория (карточки)».
3. Шлёт JSON-файл.
4. Бот парсит, валидирует, делает upsert по `external_key`.

Формат JSON для тестовых:

```json
[
  {
    "text": "Что выведет `print(0.1 + 0.2 == 0.3)`?",
    "options": ["True", "False", "Ошибка"],
    "correct_index": 1,
    "explanation": "Из-за плавающей точки 0.1+0.2 = 0.30000000000000004",
    "difficulty": 2,
    "external_key": "py-float-001"
  }
]
```

Формат для теории - см. README. `external_key` опционален (если не задан -
бот сгенерирует hash от текста).

## 16. Celery: фоновые задачи и beat

Beat schedule живёт в `pylevelup/celery_app.py`:

```python
celery.conf.beat_schedule = {
    "send-daily-reminders": {
        "task": "pylevelup.tasks.reminders.send_daily_reminders",
        "schedule": crontab(hour=settings.daily_reminder_hour_utc, minute=0),
    },
    "refresh-ranking": {
        "task": "pylevelup.tasks.ranking.refresh_ranking",
        "schedule": timedelta(minutes=settings.ranking_refresh_minutes),
    },
}
```

Procfile запускает три отдельных процесса:

```
web: python -m pylevelup
worker: celery -A pylevelup.celery_app worker -l info
beat: celery -A pylevelup.celery_app beat -l info
```

Локально для разработки достаточно `web`. Celery нужен только если тестируете
рассылки или пересчёт рейтинга.

## 17. Как добавить новую фичу

Сценарий: «хочу добавить кнопку Pomodoro-таймер в `/panel`».

1. **Модель** (если нужна новая таблица): добавить класс в `db/models.py`,
   запустить `alembic revision --autogenerate -m "add pomodoro_session"`,
   проверить миграцию, применить.

2. **Репозиторий**: создать `repositories/pomodoro_repo.py`, импортнуть в
   `repositories/__init__.py`.

3. **Сервис** (если логика сложнее CRUD): создать `services/pomodoro.py`.

4. **States** (если нужен многошаговый ввод): добавить
   `states/pomodoro.py` с `StatesGroup`.

5. **Handler**: создать `handlers/pomodoro.py`, объявить `router =
   Router(name=...)`. Зарегистрировать в `handlers/__init__.py`:
   ```python
   from pylevelup.handlers import pomodoro
   def build_root_router():
       root = Router()
       ...
       root.include_router(pomodoro.router)
       return root
   ```

6. **Команда в меню**: добавить `BotCommand(...)` в `bot.py`.

7. **Кнопка в `/panel`**: добавить пункт в `_root_menu()` в
   `handlers/admin_panel.py` (для админов) или в соответствующее меню для
   юзеров.

8. **Тесты**: добавить в `tests/` (юнит-тест сервиса), опционально smoke-test
   через `aiogram-tests`.

9. **Документация**: обновить README и DEVELOPER_GUIDE.

## 18. Локальная разработка и тестирование

Минимальный сетап:

```bash
cp .env.example .env
# заполнить BOT_TOKEN (создай тест-бота через BotFather)
# OWNER_TELEGRAM_ID - твой ID из @userinfobot

docker compose up -d postgres redis
uv sync
alembic upgrade head
python -m pylevelup
```

Запустить юнит-тесты:

```bash
pytest tests/
```

Запустить линтер:

```bash
ruff check pylevelup/
```

Запустить с автоперезапуском (требует `watchexec`):

```bash
watchexec -r -e py 'python -m pylevelup'
```

## 19. Стиль кода и инварианты

- **Без комментариев в коде.** Имена функций/переменных должны говорить сами
  за себя. Исключение: если приходится разруливать неочевидный edge case или
  обходить баг во внешней либе - короткий комментарий.
- **Без em-dash (`-`).** Только обычный дефис (`-`).
- **Импорты только сверху файла.** Никаких локальных `import foo` внутри
  функций - только при разруливании circular import.
- **`safe_edit_text` / `edit_or_send` вместо `message.edit_text`.**
- **`pg_insert(...).on_conflict_do_update(...)`** для всех upsert-ов.
- **Транзакции открываются в handler-е**, не в репозитории.
- **`ruff check pylevelup/` должен проходить до commit-а.**
- **Никогда не пушим в `main`/`master` напрямую.** Всегда через ветку и PR.
- **Никогда не `--force` в shared-ветки.**
- **Не коммитим `.env` или файлы с секретами.**
