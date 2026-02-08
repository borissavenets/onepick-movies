"""Handler for /start command with deep-link parsing."""

import re

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message

from app.bot.keyboards import kb_start
from app.bot.messages import start_message
from app.bot.sender import safe_send_message
from app.bot.session import flow_sessions, rec_sessions
from app.logging import get_logger
from app.storage import EventsRepo, UsersRepo, get_session_factory

router = Router(name="start")
logger = get_logger(__name__)

# Deep-link pattern: post_<post_id>_v<variant_id>
DEEPLINK_PATTERN = re.compile(r"^post_([a-zA-Z0-9_-]+)_v([a-zA-Z0-9_-]+)$")


def parse_deeplink(payload: str | None) -> dict[str, str] | None:
    """Parse deep-link payload.

    Expected format: post_<post_id>_v<variant_id>

    Args:
        payload: Raw deep-link payload string

    Returns:
        Dictionary with post_id and variant_id, or None if invalid
    """
    if not payload:
        return None

    match = DEEPLINK_PATTERN.match(payload)
    if match:
        return {
            "post_id": match.group(1),
            "variant_id": match.group(2),
        }

    return None


@router.message(CommandStart())
async def handle_start(message: Message, command: CommandObject) -> None:
    """Handle the /start command with optional deep-link.

    Args:
        message: Incoming message from the user
        command: Parsed command with args
    """
    user = message.from_user
    if not user:
        return

    user_id = str(user.id)
    logger.info(f"User {user_id} started the bot")

    # Reset flow session
    flow_sessions.reset_flow(user_id)

    # Parse deep-link if present
    deeplink_data = parse_deeplink(command.args)

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Get or create user
        users_repo = UsersRepo(session)
        await users_repo.get_or_create_user(user_id)
        await users_repo.update_last_seen(user_id)

        # Log events
        events_repo = EventsRepo(session)

        # Build event payload
        payload = {
            "username": user.username,
            "first_name": user.first_name,
        }

        if deeplink_data:
            payload["post_id"] = deeplink_data["post_id"]
            payload["variant_id"] = deeplink_data["variant_id"]

            # Store ref info in session
            flow_sessions.set_ref(user_id, deeplink_data)
            rec_sessions.set_ref(user_id, deeplink_data)

            # Log bot click from post
            await events_repo.log_event(
                event_name="bot_click_from_post",
                user_id=user_id,
                post_id=deeplink_data["post_id"],
                payload={
                    "variant_id": deeplink_data["variant_id"],
                },
            )

        # Log bot start
        await events_repo.log_event(
            event_name="bot_start",
            user_id=user_id,
            payload=payload,
        )

    # Send welcome message
    await safe_send_message(
        bot=message.bot,
        chat_id=message.chat.id,
        text=start_message(),
        reply_markup=kb_start(),
    )
