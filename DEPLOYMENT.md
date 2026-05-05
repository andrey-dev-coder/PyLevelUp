# PyLevelUp Deployment Guide

В этом файле описаны два сценария: локальный запуск проекта (для разработки и теста) и деплой на
[Railway.app](https://railway.app/) для продакшена.

## 1. Требования

- Python 3.11.4 (например через [pyenv](https://github.com/pyenv/pyenv))
- Docker и Docker Compose v2
- Учётка Telegram и токен бота от [@BotFather](https://t.me/BotFather)
- Учётка на Railway (для облачного деплоя)

## 2. Локальный запуск

### 2.1. Клонирование

```bash
git clone https://github.com/andrey-dev-coder/PyLevelUp.git
cd PyLevelUp
```

### 2.2. Переменные окружения

```bash
cp .env.example .env
```

Заполните `.env`:

```env
BOT_TOKEN=ваш_токен_от_BotFather

DATABASE_URL=postgresql+asyncpg://pylevelup:pylevelup@localhost:5432/pylevelup
DATABASE_URL_SYNC=postgresql+psycopg2://pylevelup:pylevelup@localhost:5432/pylevelup

REDIS_URL=redis://localhost:6379/0
REDIS_FSM_URL=redis://localhost:6379/1
REDIS_CACHE_URL=redis://localhost:6379/2

CELERY_BROKER_URL=redis://localhost:6379/3
CELERY_RESULT_BACKEND=redis://localhost:6379/4

DAILY_QUESTION_LIMIT=50
SESSION_TIMEOUT_SECONDS=3600
DAILY_REMINDER_HOUR_UTC=9
RANKING_REFRESH_MINUTES=15

LOG_LEVEL=INFO
```

### 2.3. Запуск инфраструктуры

```bash
docker compose up -d postgres redis rabbitmq
```

При желании можно запустить весь стек целиком:

```bash
docker compose up --build
```

Тогда бот, воркер и beat поднимутся в контейнерах автоматически.

### 2.4. Запуск без Docker (нативно)

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

alembic upgrade head
python -m scripts.seed_questions

python -m pylevelup
```

В отдельных терминалах запустите:

```bash
celery -A pylevelup.celery_app.celery_app worker --loglevel=INFO --concurrency=2
celery -A pylevelup.celery_app.celery_app beat --loglevel=INFO
```

### 2.5. Проверка

1. Откройте чат с ботом (по юзернейму, заданному в BotFather).
2. Отправьте `/start`, затем `/test`.
3. Ответьте на пару вопросов и проверьте `/stats`.

## 3. Деплой на Railway.app

Railway отлично подходит, потому что умеет одной кнопкой поднять PostgreSQL, Redis, добавить
сервисы из репозитория и переменные окружения.

### 3.1. Создание проекта

1. Зарегистрируйтесь на https://railway.app и подключите GitHub.
2. New Project -> Deploy from GitHub repo -> выберите `andrey-dev-coder/PyLevelUp`.
3. Railway сам обнаружит `Dockerfile` или `Procfile`. Можно использовать любой из вариантов.

### 3.2. Подключение PostgreSQL

1. В вашем проекте Railway: New -> Database -> PostgreSQL.
2. Railway сам создаст переменную `DATABASE_URL` и пропишет её в сервис бота через Reference Variables.
3. Никакой ручной правки URL не нужно: код сам нормализует `postgres://` и `postgresql://` в asyncpg формат, а `DATABASE_URL_SYNC` для миграций тоже выводится автоматически.

### 3.3. Подключение Redis

1. New -> Database -> Redis.
2. Railway создаст переменную `REDIS_URL` (формат `redis://default:PASSWORD@HOST:PORT`).
3. Никакой ручной правки не нужно: переменные `REDIS_FSM_URL`, `REDIS_CACHE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` автоматически выводятся из `REDIS_URL` с индексами /1, /2, /3, /4.

### 3.4. RabbitMQ (опционально)

Если хочется поменять брокер с Redis на RabbitMQ:

1. New -> Add a Service -> Docker Image -> `rabbitmq:3-management-alpine`.
2. Установите переменные `RABBITMQ_DEFAULT_USER`, `RABBITMQ_DEFAULT_PASS`.
3. В сервисе бота поменяйте `CELERY_BROKER_URL=amqp://USER:PASS@HOST:5672//`.

Для этого проекта по умолчанию Redis-брокера достаточно: меньше сервисов, проще.

### 3.5. Переменные окружения сервиса

Минимальный набор для Railway (всё остальное автоматически выводится из этих значений):

```
BOT_TOKEN=ваш_токен_от_BotFather
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
OWNER_TELEGRAM_ID=896090535
DEFAULT_ACCESS_CODE=pylevelup_2026
```

При добавлении PostgreSQL и Redis сервисов в проект Railway сам подставит эти Reference Variables. Если выбираете значения вручную, скопируйте `DATABASE_URL` и `REDIS_URL` из вкладок Variables соответствующих сервисов и вставьте в Raw Editor.

Дополнительные параметры (опционально):

```
DAILY_QUESTION_LIMIT=50
SESSION_TIMEOUT_SECONDS=3600
DAILY_REMINDER_HOUR_UTC=9
RANKING_REFRESH_MINUTES=15
LOG_LEVEL=INFO
```

### 3.6. Команды запуска

Railway по умолчанию использует `Procfile`. В этом проекте он содержит четыре процесса:

```
web:     python -m pylevelup
worker:  celery -A pylevelup.celery_app.celery_app worker --loglevel=INFO --concurrency=2
beat:    celery -A pylevelup.celery_app.celery_app beat --loglevel=INFO
release: alembic upgrade head && python -m scripts.seed_questions
```

В Railway каждый Procfile-процесс это отдельная replica. Чтобы поднять три процесса:

1. Создайте сервис `pylevelup-bot` -> Settings -> Start Command:
   `python -m pylevelup`
2. Дублируйте сервис как `pylevelup-worker` -> Start Command:
   `celery -A pylevelup.celery_app.celery_app worker --loglevel=INFO --concurrency=2`
3. Дублируйте сервис как `pylevelup-beat` -> Start Command:
   `celery -A pylevelup.celery_app.celery_app beat --loglevel=INFO`

Все три сервиса используют один и тот же образ и одни и те же `.env` переменные.

В сервисе `pylevelup-bot` дополнительно настройте Pre-Deploy Command:
`alembic upgrade head && python -m scripts.seed_questions`. Эта команда применит миграции и
загрузит банк вопросов перед каждым деплоем (seed идемпотентен за счёт `external_key`).

Альтернатива: оставить только основной сервис с `Procfile`, а воркер и beat поднимать как
отдельные сервисы из того же репозитория с переопределённой Start Command.

### 3.7. Проверка

1. После деплоя зайдите в логи `pylevelup-bot`. Должна быть строка `bot_started username=...`.
2. В чате бота отправьте `/start`, `/test`, `/stats`, `/info`.
3. В логах `pylevelup-worker` и `pylevelup-beat` убедитесь, что задачи `refresh_ranking` и
   `send_daily_reminders` корректно регистрируются.

## 4. Что мониторить

- `bot_started` структурированный лог при поднятии.
- `ranking_refreshed users=N` лог фоновой задачи: если N не растёт, значит, ранжирование не
  применяется.
- Размер очереди Celery в Redis (`LLEN celery`): рост означает, что воркеры не справляются.
- Список активных ключей `pylevelup:session:*` в Redis: оценка количества активных сессий.

## 5. Обновление

```bash
git pull
docker compose up -d --build
docker compose exec bot alembic upgrade head
docker compose exec bot python -m scripts.seed_questions
```

На Railway достаточно мерджа в основную ветку, релиз произойдёт автоматически (Pre-Deploy
команда применит миграции и засидит новые вопросы).
