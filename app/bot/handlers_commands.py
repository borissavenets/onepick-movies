"""Handlers for bot commands (/help, /reset, /history, /favorites)."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.messages import (
    CREDITS_MESSAGE,
    HELP_MESSAGE,
    favorites_empty,
    favorites_header,
    favorites_item,
    history_empty,
    history_header,
    history_item,
    reset_done,
)
from app.bot.sender import safe_send_message
from app.bot.session import flow_sessions, rec_sessions
from app.logging import get_logger
from app.storage import (
    EventsRepo,
    FavoritesRepo,
    FeedbackRepo,
    RecsRepo,
    UsersRepo,
    get_session_factory,
)

router = Router(name="commands")
logger = get_logger(__name__)


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    """Handle the /help command."""
    await safe_send_message(
        bot=message.bot,
        chat_id=message.chat.id,
        text=HELP_MESSAGE,
    )


@router.message(Command("credits"))
async def handle_credits(message: Message) -> None:
    """Handle the /credits command - show attribution info."""
    await safe_send_message(
        bot=message.bot,
        chat_id=message.chat.id,
        text=CREDITS_MESSAGE,
    )


@router.message(Command("reset"))
async def handle_reset(message: Message) -> None:
    """Handle the /reset command - clear user preferences."""
    user = message.from_user
    if not user:
        return

    user_id = str(user.id)
    logger.info(f"User {user_id} requested reset")

    # Clear session caches
    flow_sessions.clear(user_id)
    rec_sessions.clear(user_id)

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Reset user in database
        users_repo = UsersRepo(session)
        await users_repo.reset_user(user_id)

        # Log event
        events_repo = EventsRepo(session)
        await events_repo.log_event(
            event_name="reset",
            user_id=user_id,
            payload={},
        )

    await safe_send_message(
        bot=message.bot,
        chat_id=message.chat.id,
        text=reset_done(),
    )


@router.message(Command("history"))
async def handle_history(message: Message) -> None:
    """Handle the /history command - show recent picks."""
    user = message.from_user
    if not user:
        return

    user_id = str(user.id)
    logger.info(f"User {user_id} requested history")

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Get recent recommendations
        recs_repo = RecsRepo(session)
        feedback_repo = FeedbackRepo(session)

        history = await recs_repo.list_user_history(user_id, limit=10)

        if not history:
            await safe_send_message(
                bot=message.bot,
                chat_id=message.chat.id,
                text=history_empty(),
            )
            return

        # Build history message
        lines = [history_header()]

        for i, rec in enumerate(history, 1):
            title = rec.item.title if rec.item else "Unknown"

            # Get last feedback action for this rec
            feedbacks = await feedback_repo.get_feedback_for_rec(rec.rec_id)
            action = feedbacks[0].action if feedbacks else None

            lines.append(history_item(i, title, action))

        await safe_send_message(
            bot=message.bot,
            chat_id=message.chat.id,
            text="\n".join(lines),
        )


@router.message(Command("favorites"))
async def handle_favorites(message: Message) -> None:
    """Handle the /favorites command - show saved favorites."""
    user = message.from_user
    if not user:
        return

    user_id = str(user.id)
    logger.info(f"User {user_id} requested favorites")

    session_factory = get_session_factory()
    async with session_factory() as session:
        favorites_repo = FavoritesRepo(session)
        favorites = await favorites_repo.list_favorites(user_id, limit=50)

        if not favorites:
            await safe_send_message(
                bot=message.bot,
                chat_id=message.chat.id,
                text=favorites_empty(),
            )
            return

        # Build favorites message
        lines = [favorites_header()]

        for i, fav in enumerate(favorites, 1):
            title = fav.item.title if fav.item else "Unknown"
            lines.append(favorites_item(i, title))

        await safe_send_message(
            bot=message.bot,
            chat_id=message.chat.id,
            text="\n".join(lines),
        )
