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


def list_topic_filter(category_key: str) -> list[str] | None:
    if category_key == ALL_CATEGORY_KEY:
        return None
    if category_key not in CATEGORY_BY_KEY:
        return None
    return [category_key]


def display_name(category_key: str) -> str:
    if category_key == ALL_CATEGORY_KEY:
        return "Все темы"
    cat = CATEGORY_BY_KEY.get(category_key)
    return cat.title if cat else category_key


SESSION_MODES: tuple[tuple[str, int | None], ...] = (
    ("5 вопросов", 5),
    ("10 вопросов", 10),
    ("20 вопросов", 20),
    ("50 вопросов (дневная норма)", 50),
    ("Без лимита", None),
)
