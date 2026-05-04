from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class SpacedRepetitionState:
    ease_factor: float
    interval_days: int
    repetitions: int
    next_review_at: datetime


class SpacedRepetitionEngine:
    INITIAL_EASE = 2.5
    MIN_EASE = 1.3

    def evaluate(
        self,
        prior_ease: float | None,
        prior_interval_days: int | None,
        prior_repetitions: int | None,
        quality: int,
        now: datetime | None = None,
    ) -> SpacedRepetitionState:
        if not 0 <= quality <= 5:
            raise ValueError("quality must be between 0 and 5")

        ease = prior_ease if prior_ease is not None else self.INITIAL_EASE
        interval = prior_interval_days if prior_interval_days is not None else 0
        repetitions = prior_repetitions if prior_repetitions is not None else 0
        reference = now or datetime.now(UTC)

        if quality < 3:
            repetitions = 0
            interval = 1
        else:
            repetitions += 1
            if repetitions == 1:
                interval = 1
            elif repetitions == 2:
                interval = 6
            else:
                interval = max(1, round(interval * ease))

        ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        if ease < self.MIN_EASE:
            ease = self.MIN_EASE

        next_review_at = reference + timedelta(days=interval)
        return SpacedRepetitionState(
            ease_factor=round(ease, 4),
            interval_days=interval,
            repetitions=repetitions,
            next_review_at=next_review_at,
        )

    @staticmethod
    def quality_from_outcome(is_correct: bool, response_time_ms: int | None) -> int:
        if not is_correct:
            return 1
        if response_time_ms is None:
            return 4
        if response_time_ms < 5_000:
            return 5
        if response_time_ms < 15_000:
            return 4
        return 3
