from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    key: str
    title: str
    short: str


CATEGORIES: tuple[Category, ...] = (
    Category(key="python", title="Python (язык и стандарт)", short="Python"),
    Category(key="algorithms", title="Алгоритмы и структуры данных", short="Алгоритмы"),
    Category(key="algorithms_advanced", title="Алгоритмы (продвинутые)", short="Алгоритмы+"),
    Category(key="async", title="Асинхронность и многопоточность", short="Async"),
    Category(key="sql", title="SQL и базы данных", short="SQL"),
    Category(key="db_advanced", title="БД продвинуто (репликация, шардинг, MVCC)", short="БД+"),
    Category(key="http", title="HTTP и REST", short="HTTP"),
    Category(key="django", title="Django и Django ORM", short="Django"),
    Category(key="fastapi", title="FastAPI и веб-фреймворки Python", short="FastAPI"),
    Category(key="caching", title="Кэширование и Redis", short="Кэш"),
    Category(key="system_design", title="Системный дизайн бэкенда", short="System Design"),
    Category(key="microservices", title="Микросервисы и архитектура", short="Микросервисы"),
    Category(key="testing", title="Тестирование и QA", short="Testing"),
    Category(key="os_linux", title="OS и Linux для бэкендера", short="OS/Linux"),
)

CATEGORY_BY_KEY: dict[str, Category] = {c.key: c for c in CATEGORIES}
ALL_CATEGORY_KEY = "all"

_CUSTOM_CACHE: dict[str, Category] = {}


def set_custom_categories(entries: list[tuple[str, str, str | None]]) -> None:
    _CUSTOM_CACHE.clear()
    for key, title, short in entries:
        _CUSTOM_CACHE[key] = Category(key=key, title=title, short=short or title)


def add_custom_category(key: str, title: str, short: str | None) -> None:
    _CUSTOM_CACHE[key] = Category(key=key, title=title, short=short or title)


def remove_custom_category(key: str) -> None:
    _CUSTOM_CACHE.pop(key, None)


def custom_categories() -> tuple[Category, ...]:
    return tuple(_CUSTOM_CACHE.values())


def all_categories() -> tuple[Category, ...]:
    return CATEGORIES + custom_categories()


def all_category_keys() -> set[str]:
    return {c.key for c in CATEGORIES} | set(_CUSTOM_CACHE.keys())


def list_topic_filter(category_key: str) -> list[str] | None:
    if category_key == ALL_CATEGORY_KEY:
        return None
    if category_key in CATEGORY_BY_KEY or category_key in _CUSTOM_CACHE:
        return [category_key]
    return None


def display_name(category_key: str) -> str:
    if category_key == ALL_CATEGORY_KEY:
        return "Все темы"
    cat = CATEGORY_BY_KEY.get(category_key) or _CUSTOM_CACHE.get(category_key)
    return cat.title if cat else category_key


def short_name(category_key: str) -> str:
    if category_key == ALL_CATEGORY_KEY:
        return "Все"
    cat = CATEGORY_BY_KEY.get(category_key) or _CUSTOM_CACHE.get(category_key)
    return cat.short if cat else category_key


SESSION_MODES: tuple[tuple[str, int | None], ...] = (
    ("5 вопросов", 5),
    ("10 вопросов", 10),
    ("20 вопросов", 20),
    ("50 вопросов (дневная норма)", 50),
    ("Без лимита", None),
)


@dataclass(frozen=True)
class Specialization:
    key: str
    title: str
    topics: tuple[str, ...]


SPECIALIZATIONS: tuple[Specialization, ...] = (
    Specialization(
        key="all",
        title="Все темы",
        topics=tuple(c.key for c in CATEGORIES),
    ),
    Specialization(
        key="python_backend",
        title="Python Backend",
        topics=(
            "python",
            "algorithms",
            "async",
            "sql",
            "http",
            "fastapi",
            "caching",
            "testing",
            "os_linux",
        ),
    ),
    Specialization(
        key="python_senior",
        title="Python Backend (senior)",
        topics=(
            "python",
            "algorithms",
            "algorithms_advanced",
            "async",
            "sql",
            "db_advanced",
            "http",
            "fastapi",
            "caching",
            "testing",
            "os_linux",
            "system_design",
            "microservices",
        ),
    ),
    Specialization(
        key="django_dev",
        title="Django разработчик",
        topics=(
            "python",
            "django",
            "sql",
            "http",
            "caching",
            "testing",
            "async",
        ),
    ),
    Specialization(
        key="fastapi_dev",
        title="FastAPI разработчик",
        topics=(
            "python",
            "async",
            "http",
            "fastapi",
            "sql",
            "caching",
            "testing",
            "system_design",
        ),
    ),
    Specialization(
        key="junior_python",
        title="Junior Python",
        topics=(
            "python",
            "algorithms",
            "sql",
            "http",
            "testing",
        ),
    ),
)

SPECIALIZATIONS_BY_KEY: dict[str, Specialization] = {s.key: s for s in SPECIALIZATIONS}
