"""Router configuration and wiring for all bot handlers."""

from aiogram import Dispatcher, Router

from app.bot.handlers_commands import router as commands_router
from app.bot.handlers_feedback import router as feedback_router
from app.bot.handlers_flow import router as flow_router
from app.bot.handlers_reactions import router as reactions_router
from app.bot.handlers_start import router as start_router

main_router = Router(name="main")


def setup_routers(dp: Dispatcher) -> None:
    """Wire all routers to the dispatcher.

    Order matters - more specific handlers should be included first.
    Start handler is included first as it handles /start command.
    Commands handler includes /help, /reset, /history, /favorites.
    Flow handler includes the question flow callbacks.
    Feedback handler includes recommendation action callbacks.

    Args:
        dp: The aiogram Dispatcher instance
    """
    # Include routers in order
    main_router.include_router(start_router)
    main_router.include_router(commands_router)
    main_router.include_router(flow_router)
    main_router.include_router(feedback_router)
    main_router.include_router(reactions_router)

    dp.include_router(main_router)
