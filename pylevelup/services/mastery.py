from dataclasses import dataclass


@dataclass(frozen=True)
class MasteryLevel:
    code: str
    label: str
    icon: str
    min_answered: int
    min_accuracy: float


MASTERY_LEVELS: tuple[MasteryLevel, ...] = (
    MasteryLevel(code="none", label="Новичок", icon="·", min_answered=0, min_accuracy=0.0),
    MasteryLevel(code="bronze", label="Bronze", icon="🥉", min_answered=5, min_accuracy=50.0),
    MasteryLevel(code="silver", label="Silver", icon="🥈", min_answered=20, min_accuracy=60.0),
    MasteryLevel(code="gold", label="Gold", icon="🥇", min_answered=50, min_accuracy=75.0),
    MasteryLevel(code="diamond", label="Diamond", icon="💎", min_answered=100, min_accuracy=90.0),
)


def compute_level(answered: int, accuracy_percent: float) -> MasteryLevel:
    current = MASTERY_LEVELS[0]
    for level in MASTERY_LEVELS:
        if answered >= level.min_answered and accuracy_percent >= level.min_accuracy:
            current = level
    return current


def next_level(answered: int, accuracy_percent: float) -> MasteryLevel | None:
    current = compute_level(answered, accuracy_percent)
    idx = MASTERY_LEVELS.index(current)
    if idx + 1 >= len(MASTERY_LEVELS):
        return None
    return MASTERY_LEVELS[idx + 1]


__all__ = ["MASTERY_LEVELS", "MasteryLevel", "compute_level", "next_level"]
