from aiogram import Router

from pylevelup.handlers import (
    achievements,
    admin,
    ai_helper,
    bookmarks,
    broadcast,
    cheatsheet,
    daily,
    dashboard,
    hints,
    import_questions,
    info,
    mock,
    open_questions,
    reports,
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
        import_questions.router,
        dashboard.router,
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
        reports.router,
        open_questions.router,
        ai_helper.router,
    )
    return router


__all__ = ["build_root_router"]
