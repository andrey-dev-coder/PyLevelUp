from dataclasses import dataclass


@dataclass(frozen=True)
class AchievementDef:
    code: str
    title: str
    description: str
    icon: str
    sort_order: int


ACHIEVEMENTS: tuple[AchievementDef, ...] = (
    AchievementDef("first_step", "Первый шаг", "Ответил на первый вопрос", "🌱", 10),
    AchievementDef("ten_correct", "Меткий стрелок", "10 правильных ответов", "🎯", 20),
    AchievementDef("hundred_correct", "Сотка", "100 правильных ответов", "💯", 30),
    AchievementDef("five_hundred_correct", "Гуру", "500 правильных ответов", "🧙", 40),
    AchievementDef("streak_3", "Втянулся", "Заходил 3 дня подряд", "🔥", 50),
    AchievementDef("streak_7", "Неделя силы", "Заходил 7 дней подряд", "⚡", 60),
    AchievementDef("streak_30", "Железная воля", "Заходил 30 дней подряд", "🏔️", 70),
    AchievementDef("mock_passed", "Готов к собесу", "Прошёл mock-собеседование", "🎓", 80),
    AchievementDef("mock_perfect", "Идеал", "Mock 20/20", "🏆", 90),
    AchievementDef("daily_5", "Челленджист", "5 правильных в челлендже дня", "🗓️", 100),
    AchievementDef("daily_25", "Без выходных", "25 правильных в челлендже дня", "📆", 110),
    AchievementDef("bookmarks_10", "Коллекционер", "10 закладок", "⭐", 120),
    AchievementDef("topic_bronze", "Бронзовый призёр", "Bronze в любой теме", "🥉", 130),
    AchievementDef("topic_gold", "Золотой стандарт", "Gold в любой теме", "🥇", 140),
    AchievementDef("topic_diamond", "Алмазный лорд", "Diamond в любой теме", "💎", 150),
)

ACHIEVEMENTS_BY_CODE: dict[str, AchievementDef] = {a.code: a for a in ACHIEVEMENTS}


__all__ = ["ACHIEVEMENTS", "ACHIEVEMENTS_BY_CODE", "AchievementDef"]
