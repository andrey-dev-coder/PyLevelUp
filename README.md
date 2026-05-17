# PyLevelUp

Telegram-бот для подготовки к техническим собеседованиям. Стартовал как тренажёр
по Python, превратился в платформу с учебными планами, открытыми вопросами,
mock-собесами, импортом контента через JSON и развёрнутой админ-панелью.

Production: [@pylevelup_bot](https://t.me/pylevelup_bot)

## Содержание

- [Что умеет бот](#что-умеет-бот)
- [Стек](#стек)
- [Быстрый запуск](#быстрый-запуск)
- [Команды](#команды)
- [Структура репозитория](#структура-репозитория)
- [Документация](#документация)

## Что умеет бот

### Для пользователя

- **`/test`** - адаптивная сессия тестовых вопросов с вариантами ответа. Алгоритм
  интервального повторения (SuperMemo-2) выбирает что повторять, что показать
  новое, с какой сложностью. Пользователь выбирает категорию (Python, SQL,
  HTTP, async, FastAPI, Django, алгоритмы, system design, microservices,
  caching, OS/Linux, db_advanced, testing, или любую кастомную) и количество
  вопросов.
- **`/study`** - режим «карточек» для теории: вопрос → «Показать ответ» →
  эталонный ответ + чек-лист. Хранится в отдельной таблице `open_questions`.
- **`/mock`** - mock-собеседование: фикс-набор вопросов из разных тем,
  засчитывается отдельно от тренировок. Есть пресеты под специализации и режим
  «свой набор тем».
- **`/daily`** - челлендж дня: 5-10 вопросов из миксованных тем. Записывается
  в `daily_challenges`.
- **`/paths`** - учебные планы (roadmaps): последовательность блоков с
  требованиями по точности; следующий блок открывается когда текущий пройден.
- **`/stats`** - личная статистика: точность, стрики, рейтинг, лучшие/слабые
  темы.
- **`/bookmarks`** - закладки на сложные вопросы.
- **`/search`** - поиск вопросов по тексту.
- **`/cheatsheet`** - генерация шпаргалок по теме.
- **`/hints`** - лимитированные подсказки на сессию (3/день).
- После сессии - экран «Личные рекорды» (точность за всю историю, лучший
  день, точность по теме сессии, текущий и максимальный стрик, плашка «Новый
  личный рекорд» при побитии).
- Напоминания о тренировках (Celery Beat).
- Ачивки - за стрики, накопленный объём, точность.

### Для админа (owner)

`OWNER_TELEGRAM_ID` из `.env` единолично имеет доступ к админским командам.

- **`/panel`** - единая кнопочная панель. Корневое меню:
  - 👥 **Пользователи** - три вкладки: активные, ожидают одобрения, забаненные.
    Из карточки юзера: статистика, темы доступа (whitelist), бан/разбан,
    написать (📨), удалить (с каскадом по БД), одобрить (для pending).
  - 🔑 **Коды доступа** - создание/редактирование «кодовых слов». Каждый код
    привязан к набору тем: пользователь вводит код → авторизуется и получает
    whitelist именно этих тем. Глобальный `ACCESS_CODE` из env даёт все темы.
  - 📝 **Редактор вопросов** - список категорий, постраничный список вопросов
    и карточек, изменение текста/вариантов/правильного ответа/пояснения/
    сложности, скрытие/активация (`is_active`), удаление (каскадно). Глобальный
    и категорийный поиск по тексту/ID (`#1234`).
  - 🛣 **Учебные планы** - CRUD планов: блоки по темам с требованиями
    `min_questions` и `required_accuracy`.
  - 🗑 **Удалить категорию** - каскадный wipe кастомной категории:
    вопросы, теория, daily_challenges, ссылки в `user_topic_access` и в
    `access_codes.allowed_topics`.
  - 📥 **Импорт вопросов** - JSON-импорт тестовых вопросов И теоретических
    карточек (отдельный режим). Распарсивается, валидируется, делается upsert
    по `external_key`.
  - 🚩 **Жалобы** - поток жалоб на вопросы от пользователей.
  - 📊 **Дашборд** - DAU/MAU, общая активность, топ-проваленных вопросов.
  - 📢 **Рассылка** - `/broadcast`.

- Параллельно остаются прямые команды:
  - `/dm <user_id или @username> <текст>` - отправить сообщение от имени бота.
  - `/user_stats <id>` - полный текстовый отчёт по пользователю.
  - `/user_topics <id>` - настройка whitelist тем у конкретного пользователя.
  - `/import` - JSON-импорт.
  - `/categories` - управление кастомными темами.
  - `/setcode <CODE>` - задать глобальный код доступа.
  - `/broadcast <текст>` / `/broadcast_test <текст>`.
  - `/reports`, `/admin`.

## Стек

- Python 3.11+
- aiogram 3.x (async polling)
- SQLAlchemy 2.0 async + Alembic
- PostgreSQL 16 (JSONB для опций/чек-листов)
- Redis 7 (FSM-storage, кэш активной тест-сессии)
- Celery 5 + beat (рассылки, пересчёт рейтинга, ачивки)
- pydantic-settings, structlog, ruff
- Docker / docker-compose, Railway-ready

## Быстрый запуск

```bash
git clone https://github.com/andrey-dev-coder/PyLevelUp.git
cd PyLevelUp
cp .env.example .env
# заполните как минимум: BOT_TOKEN, OWNER_TELEGRAM_ID, DATABASE_URL, REDIS_URL
docker compose up -d postgres redis
uv sync   # либо: pip install -e .
alembic upgrade head
python -m pylevelup
```

Подробнее по запуску, переменным окружения и деплою на Railway - см.
[DEPLOYMENT.md](DEPLOYMENT.md).

## Команды

Все команды описаны выше в разделе «Что умеет бот». Полный реестр команд с
порядком объявления (то, что показывается в Telegram-клиенте «Меню») - в
[`pylevelup/bot.py`](pylevelup/bot.py).

## Структура репозитория

```
pylevelup/
  config.py                  pydantic-settings + .env
  bot.py                     Bot/Dispatcher/Storage init + command menu
  __main__.py                entrypoint (python -m pylevelup)
  celery_app.py              Celery + beat schedule
  categories.py              builtin category map + custom registry cache

  db/
    base.py                  DeclarativeBase + naming convention
    session.py               async engine, sessionmaker
    models.py                все ORM-модели

  repositories/              тонкие классы вокруг AsyncSession
    user_repo.py             поиск/фильтрация/удаление юзеров
    question_repo.py         CRUD тестовых вопросов + search
    open_question_repo.py    CRUD теории + search
    learning_path_repo.py    планы, блоки, прогресс
    access_code_repo.py      коды доступа
    topic_access_repo.py     whitelist тем у юзера
    ...                      attempts, bookmarks, achievements, mocks и др.

  services/
    spaced_repetition.py     чистая функция SM-2
    session_cache.py         Redis state машина для активной сессии
    test_session_service.py  оркестратор тест-сессии (старт, ответ, flush)
    stats_service.py         агрегации с оконными функциями
    ranking_service.py       пересчёт рейтинга
    broadcast.py             рассылка пакетами
    topic_access.py          бизнес-логика whitelist тем

  handlers/                  все aiogram routers (по фиче на файл)
    start.py                 /start, регистрация, ввод кода доступа
    test.py                  /test, ans:*, итоги сессии
    study.py                 /study, режим карточек теории
    mock.py                  /mock
    daily.py                 /daily
    learning_paths.py        /paths (юзер)
    stats.py                 /stats
    bookmarks.py, search.py, hints.py, cheatsheet.py
    admin.py                 /broadcast, /setcode, /reports, /admin
    admin_panel.py           /panel - корневая кнопочная панель
    admin_editor.py          редактор вопросов и теории (CRUD per-row)
    admin_paths.py           админ-CRUD учебных планов
    user_admin.py            /user_stats, /user_topics, /dm
    import_questions.py      /import (JSON, вопросы и теория)
    reports.py, dashboard.py, broadcast.py

  middlewares/
    user.py                  upsert юзера на каждом апдейте
    access.py                проверка авторизации, бан, whitelist тем

  states/                    StatesGroup-ы для FSM (mock, import, search...)
  keyboards/                 общие InlineKeyboardBuilder-ы
  tasks/                     Celery tasks (reminders, ranking, achievements)
  utils/                     edit.py (safe_edit_text), ...

migrations/versions/         Alembic-миграции
data/                        начальные JSON-вопросы и темы

ARCHITECTURE.md              устройство БД, кэш, SR, оконные функции
DEVELOPER_GUIDE.md           гайд по коду: как добавить фичу, паттерны
OPERATIONS.md                runbook админа: команды, деплой, инциденты
DEPLOYMENT.md                локальный запуск и Railway-деплой
```

## Документация

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - как устроено внутри: БД, кэш сессии,
  SuperMemo-2, оконные функции рейтинга, Celery beat.
- **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)** - подробный гайд для нового
  разработчика: где что лежит, как добавить новый handler/repo/migration,
  паттерны FSM, как работает middleware доступа, как тестировать.
- **[OPERATIONS.md](OPERATIONS.md)** - runbook администратора: все команды
  бота, типовые сценарии (выдать доступ, забанить, импорт, рассылка),
  переменные окружения, миграции, восстановление.
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - пошаговая инструкция по локальному
  запуску и деплою на Railway.

## Контакты

- Автор: Муратов Андрей
- Telegram: [@m203ac](https://t.me/m203ac)
- Issues: https://github.com/andrey-dev-coder/PyLevelUp/issues
