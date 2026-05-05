import asyncio
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from sqlalchemy.ext.asyncio import async_sessionmaker

from pylevelup.logger import get_logger
from pylevelup.repositories import UserRepository

logger = get_logger(__name__)


@dataclass
class BroadcastResult:
    total: int
    delivered: int
    blocked: int
    failed: int


class BroadcastService:
    def __init__(self, session_factory: async_sessionmaker, rate_per_second: int = 25) -> None:
        self.session_factory = session_factory
        self.rate_per_second = max(1, rate_per_second)

    async def list_recipient_ids(self) -> list[int]:
        async with self.session_factory() as db:
            users_repo = UserRepository(db)
            users = await users_repo.list_broadcast_recipients()
            return [u.telegram_id for u in users]

    async def send_to_all(self, bot: Bot, text: str) -> BroadcastResult:
        recipient_ids = await self.list_recipient_ids()
        return await self._send_batch(bot, text, recipient_ids)

    async def send_to_one(self, bot: Bot, text: str, telegram_id: int) -> BroadcastResult:
        return await self._send_batch(bot, text, [telegram_id])

    async def _send_batch(self, bot: Bot, text: str, recipient_ids: list[int]) -> BroadcastResult:
        delivered = 0
        blocked = 0
        failed = 0
        delay = 1.0 / self.rate_per_second
        for telegram_id in recipient_ids:
            try:
                await bot.send_message(telegram_id, text)
                delivered += 1
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after + 1)
                try:
                    await bot.send_message(telegram_id, text)
                    delivered += 1
                except Exception as inner:
                    failed += 1
                    logger.warning(
                        "broadcast_retry_failed",
                        telegram_id=telegram_id,
                        error=str(inner),
                    )
            except TelegramForbiddenError:
                blocked += 1
            except TelegramBadRequest as exc:
                failed += 1
                logger.warning(
                    "broadcast_bad_request",
                    telegram_id=telegram_id,
                    error=str(exc),
                )
            except Exception as exc:
                failed += 1
                logger.warning(
                    "broadcast_send_failed",
                    telegram_id=telegram_id,
                    error=str(exc),
                )
            await asyncio.sleep(delay)

        return BroadcastResult(
            total=len(recipient_ids),
            delivered=delivered,
            blocked=blocked,
            failed=failed,
        )
