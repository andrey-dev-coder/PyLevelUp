from aiogram import Router

from pylevelup.handlers import (
    achievements,
    admin,
    bookmarks,
    broadcast,
    cheatsheet,
    daily,
    hints,
    info,
    mock,
    search,
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
        mock.router,
        achievements.router,
        cheatsheet.router,
        search.router,
    )
    return router


__all__ = ["build_root_router"]
