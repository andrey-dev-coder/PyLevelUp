from aiogram import Router

from pylevelup.handlers import info, start, stats, test


def build_root_router() -> Router:
    router = Router(name="pylevelup_root")
    router.include_routers(start.router, test.router, stats.router, info.router)
    return router


__all__ = ["build_root_router"]
