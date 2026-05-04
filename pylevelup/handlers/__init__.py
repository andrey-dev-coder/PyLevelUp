from aiogram import Router

from pylevelup.handlers import admin, info, start, stats, study, test


def build_root_router() -> Router:
    router = Router(name="pylevelup_root")
    router.include_routers(
        admin.router,
        start.router,
        test.router,
        study.router,
        stats.router,
        info.router,
    )
    return router


__all__ = ["build_root_router"]
