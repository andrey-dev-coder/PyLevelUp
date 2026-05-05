from aiogram import Router

from pylevelup.handlers import (
    admin,
    bookmarks,
    broadcast,
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
    )
    return router


__all__ = ["build_root_router"]
