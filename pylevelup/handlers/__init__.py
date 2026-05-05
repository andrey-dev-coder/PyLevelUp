from aiogram import Router

from pylevelup.handlers import (
    admin,
    bookmarks,
    broadcast,
    daily,
    hints,
    info,
    start,
    stats,
    study,
    test,
)


def build_root_router() -> Router:
    router = Router(name="pylevelup_root")
    router.include_routers(
        admin.router,
        broadcast.router,
        start.router,
        test.router,
        study.router,
        stats.router,
        info.router,
        bookmarks.router,
        hints.router,
        daily.router,
    )
    return router


__all__ = ["build_root_router"]
