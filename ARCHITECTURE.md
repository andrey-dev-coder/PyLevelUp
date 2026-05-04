# PyLevelUp Architecture

Документ описывает, как устроен бот изнутри: какие технологии используются, почему именно они,
как организованы данные, где живут стейты пользователя и как работает алгоритм интервального
повторения.

## 1. Высокоуровневая схема

```
                     +-------------------+
                     |   Telegram API    |
                     +---------+---------+
                               |
                               v
+-------------+        +-------+--------+        +-------------------+
|   Celery    | <----> |   aiogram 3    | -----> |   PostgreSQL 16   |
|  Worker +   |        |   (Dispatcher  |        |  (users, items,   |
|    Beat     |        |    + routers)  |        |  progress, JSONB) |
+------+------+        +-------+--------+        +---------+---------+
       |                       |                           ^
       |                       v                           |
       |                +-------+--------+                 |
       +--------------->|     Redis      |-----------------+
                        | FSM + кэш сессии|
                        | + Celery broker|
                        +----------------+
```

## 2. Стек и обоснование

| Слой | Технология | Почему |
| --- | --- | --- |
| Telegram API | aiogram 3 | Современный async-first фреймворк, корректные dataclass-роутеры, dependency injection через workflow data, поддержка FSM и Redis storage из коробки. |
| База данных | PostgreSQL 16 | Стабильная реляционная СУБД с JSONB для гетерогенных данных (варианты ответа), оконные функции для рейтинга, надёжные транзакции. |
| ORM | SQLAlchemy 2.0 (async) | Полноценная типизация, async API, чистое разделение моделей и репозиториев. |
| Миграции | Alembic | Стандарт де-факто для SQLAlchemy. |
| Кэш и FSM | Redis 7 | Быстрая in-memory БД для FSM (`aiogram.fsm.storage.redis`) и буфера ответов сессии. Pipeline-операции для атомарных обновлений. |
| Фоновые задачи | Celery 5 | Отделение долгих задач (рассылка, пересчёт рейтинга) от хэндлеров. |
| Брокер Celery | Redis (по умолчанию) | Минимизация числа сервисов в проекте. RabbitMQ опционально доступен в `docker-compose.yml`. |
| Контейнеризация | Docker + docker-compose | Локальная разработка одной командой, Railway-ready. |
| Конфигурация | pydantic-settings | Типобезопасный `.env` парсинг, фейл-фаст при пропущенных переменных. |

## 3. Схема базы данных

| Таблица | Назначение | Ключевые поля |
| --- | --- | --- |
| `users` | Учётка Telegram-пользователя, агрегированные счётчики, рейтинг | `telegram_id` (unique), `current_streak`, `max_streak`, `total_correct`, `total_answered`, `ranking_score`, `last_ranking_position`, `reminders_enabled`, `timezone` |
| `questions` | Банк вопросов | `topic`, `difficulty`, `text`, `options` (JSONB), `correct_index`, `explanation`, `external_key` (unique) |
| `user_progress` | Состояние SR-алгоритма для пары (user, question) | `ease_factor`, `interval_days`, `repetitions`, `next_review_at`, `last_quality` |
| `attempts` | Журнал ответов, нужен для аудита и аналитики | `is_correct`, `quality`, `response_time_ms`, `session_date` |
| `daily_sessions` | Метаданные дневной сессии (счётчик ответов, статус завершения) | uniq (`user_id`, `session_date`), `questions_answered`, `correct_count`, `finished` |

### Почему JSONB для `options`

Вариантов ответа от 4 до 6, по сути это короткий список строк. Если делать отдельную таблицу
`question_options`, мы получаем JOIN на каждое получение вопроса и фрагментацию данных. Поскольку
варианты неотделимы от вопроса и не запрашиваются индивидуально, JSONB - идеальный компромисс:

- одна запись = весь вопрос с вариантами,
- PostgreSQL поддерживает индексы (GIN) и операторы `@>`, `->>`,
- легко расширить (например, добавить пометки в вариант) без миграций таблиц.

### Индексы

- `users.telegram_id` (unique) поиск пользователя по Telegram ID на каждом апдейте.
- `user_progress(user_id, next_review_at)` композитный индекс для выборки `due` вопросов.
- `attempts(user_id, session_date)` быстрая агрегация дневных результатов.

## 4. Кэш и снижение нагрузки на БД

Каждый клик по inline-кнопке это потенциальная транзакция. При 50 вопросах и параллельных
пользователях БД мгновенно становится узким местом.

PyLevelUp снимает эту нагрузку через двухуровневую запись.

### Шаг 1: запуск сессии (1 транзакция)

При `/test` бот:

1. Делает upsert пользователя.
2. Считает оставшийся дневной лимит из `daily_sessions`.
3. Выбирает `due`-вопросы через индекс `user_progress(user_id, next_review_at)`.
4. Дополняет очередь новыми вопросами, если у пользователя нет прогресса.
5. Кладёт payload в Redis.

После этого до конца сессии транзакций к БД нет (если только не сработает периодический flush).

### Шаг 2: ответы пользователя (0 транзакций по умолчанию)

Хэндлер `ans:*`:

1. Загружает state из Redis (`HGETALL`).
2. Считает `quality` по правильности и времени ответа.
3. Делает atomic-pipeline (`DEL` + `HSET` + `EXPIRE`) обратно в Redis.

Пользователь получает фидбек мгновенно, БД спит.

### Шаг 3: batch flush

Когда пользователь отвечает на 10-й вопрос, очередь заканчивается, нажимает "Завершить" или
истекает TTL (`SESSION_TIMEOUT_SECONDS`), сервис `TestSessionService.flush_session` делает один
коммит:

- `attempts` массовая вставка через `Attempt.__table__.insert()`.
- `user_progress` upsert на каждый ответ (из ON CONFLICT DO UPDATE).
- `daily_sessions` upsert агрегатов сессии.
- `users.total_correct/total_answered` инкремент через единый `UPDATE`.
- `users.current_streak` пересчёт стрика, если сессия завершена.

Итог: вместо 50 транзакций - **1 транзакция за сессию**. При этом данные не теряются: Redis
хранит pending-список с TTL, а flush происходит по нескольким триггерам.

### TTL и устойчивость

Если воркер упадёт во время сессии, Redis сам удалит ключ через `SESSION_TIMEOUT_SECONDS`. Если
пользователь вернётся в течение TTL, бот возобновит сессию с того же места. Если flush уже был, в
Redis сидит state без pending-ответов это нормально, повторного коммита не будет.

## 5. Алгоритм Spaced Repetition

Используется адаптация SuperMemo-2 (`SpacedRepetitionEngine.evaluate`).

```
quality (0..5):
    is_correct=False                -> quality = 1
    is_correct=True, RT < 5s        -> quality = 5
    is_correct=True, RT < 15s       -> quality = 4
    is_correct=True, RT >= 15s      -> quality = 3
```

```
if quality < 3:
    repetitions = 0
    interval = 1 day
else:
    repetitions += 1
    if repetitions == 1: interval = 1
    elif repetitions == 2: interval = 6
    else: interval = round(prev_interval * ease)

ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
ease = max(1.3, ease)
next_review_at = now + interval
```

Это даёт классическое поведение SM-2: ошиблись короткий интервал, ответили легко интервал
увеличивается экспоненциально, ease-factor аккуратно подстраивается. Минимум `1.3` защищает
систему от схлопывания интервалов до нуля.

`SpacedRepetitionEngine.quality_from_outcome` маппит исход теста (правильно/неправильно и время
ответа) в `quality`, чтобы хэндлеры не знали про детали алгоритма.

## 6. Рейтинг через оконные функции

`StatsService.get_user_stats` собирает позицию пользователя через подзапрос:

```sql
SELECT user_id,
       RANK() OVER (ORDER BY ranking_score DESC, total_correct DESC) AS position
FROM users
WHERE is_active = TRUE
```

Это даёт корректный rank даже при равных очках. То же делает фоновая задача `refresh_ranking`:
она считает `score = total_correct + accuracy*50 + current_streak*5 + max_streak*2` и сохраняет
позицию обратно в `users` через `UPDATE ... FROM (subquery)`.

## 7. Celery: фоновые процессы

| Задача | Расписание | Что делает |
| --- | --- | --- |
| `pylevelup.tasks.reminders.send_daily_reminders` | Каждый день в `DAILY_REMINDER_HOUR_UTC` | Рассылает напоминание всем активным пользователям с включёнными напоминаниями. Отключает напоминания тем, кто заблокировал бота. |
| `pylevelup.tasks.ranking.refresh_ranking` | Каждые `RANKING_REFRESH_MINUTES` минут | Пересчитывает `ranking_score` и `last_ranking_position` для всех пользователей. |

Celery воркер и beat запускаются как отдельные процессы (см. `Procfile` и `docker-compose.yml`).
Это критично для Railway: один процесс не может одновременно быть и beat, и воркером.

## 8. Слои и модули

```
pylevelup/
  config.py             pydantic-settings, .env
  logger.py             structlog
  bot.py                инициализация Bot/Dispatcher/Storage, поднятие polling
  __main__.py           точка входа

  db/
    base.py             DeclarativeBase + naming convention
    session.py          async engine, sessionmaker
    models.py           User, Question, UserProgress, Attempt, DailySession

  repositories/         тонкие классы вокруг сессии БД
  services/
    spaced_repetition.py   чистая функция SM-2
    session_cache.py       Redis state машина
    test_session_service.py оркестратор сессии
    stats_service.py       SQL с оконкой
    ranking_service.py     UPDATE FROM subquery

  handlers/
    start.py            /start
    test.py             /test, ans:*, test:start, test:stop
    stats.py            /stats, stats:show
    info.py             /info, info:show

  keyboards/inline.py   InlineKeyboardBuilder
  states/test.py        FSM группа TestStates
  middlewares/user.py   опциональный middleware

  tasks/
    reminders.py        рассылка
    ranking.py          пересчёт рейтинга

  celery_app.py         Celery + beat schedule
```

Зависимости пробрасываются через `dp[...]`, что соответствует рекомендациям aiogram 3 для DI:
хэндлеры объявляют параметры (`session_factory`, `session_service` и т.д.), Dispatcher их
резолвит.

## 9. Что осознанно вынесено за рамки MVP

- Голосовые объяснения и иллюстрации в вопросах: можно подложить через JSONB `options.media`.
- Ассинхронные модули "по темам": уже поддержано через `Question.topic`, нужен только UI.
- Платные подписки и премиум-вопросы: добавляются полем в `User` без боли.
