"""Channel auto-posting job.

Publishes scheduled posts to the Telegram channel with smart format rotation
and A/B time-slot tracking.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.config import config
from app.logging import get_logger

logger = get_logger(__name__)

ROTATION_ORDER: list[str] = [
    "one_pick_emotion",
    "if_liked_x_then_y",
    "fact_then_pick",
    "poll",
    "one_pick_emotion",
    "fact_then_pick",
    "bot_teaser",
]


@dataclass
class PostResult:
    """Outcome of a single channel-post attempt."""

    ok: bool
    post_id: str | None = None
    format_id: str | None = None
    error: str | None = None


def _pick_format(today_posts: list) -> str:
    """Pick next format based on how many posts were already published today.

    Uses round-robin through ROTATION_ORDER.
    If bot_teaser was already used today, skip to next.
    """
    today_count = len(today_posts)
    idx = today_count % len(ROTATION_ORDER)

    candidate = ROTATION_ORDER[idx]

    if candidate == "bot_teaser":
        already_has_teaser = any(
            _post_has_format(p, "bot_teaser") for p in today_posts
        )
        if already_has_teaser:
            # Skip bot_teaser, advance to next
            idx = (idx + 1) % len(ROTATION_ORDER)
            candidate = ROTATION_ORDER[idx]
            # If that's also bot_teaser (shouldn't happen), fall back
            if candidate == "bot_teaser":
                candidate = "one_pick_emotion"

    return candidate


def _post_has_format(post, format_id: str) -> bool:
    """Check if a post record has the given format_id."""
    if hasattr(post, "format_id"):
        return post.format_id == format_id
    meta_json = getattr(post, "meta_json", None)
    if meta_json:
        try:
            meta = json.loads(meta_json) if isinstance(meta_json, str) else meta_json
            return meta.get("format_id") == format_id
        except (json.JSONDecodeError, TypeError):
            pass
    return False


def _make_hypothesis_id(today: date, slot_index: int) -> str:
    """Build hypothesis ID for A/B tracking."""
    return f"h-{today.isoformat()}-{slot_index}"


def _make_variant_id() -> str:
    """Return variant identifier (single variant for now)."""
    return "v-a"


async def run_channel_post(slot_index: int = 0) -> PostResult:
    """Execute one channel-post cycle.

    1. Pick format via smart rotation
    2. Generate content
    3. Send to channel
    4. Save to DB + log event

    Args:
        slot_index: Which time-slot triggered this (0, 1, …)

    Returns:
        PostResult with outcome details
    """
    if not config.channel_post_enabled:
        logger.info("Channel posting disabled, skipping")
        return PostResult(ok=False, error="posting_disabled")

    if not config.channel_id:
        logger.warning("CHANNEL_ID not set, skipping channel post")
        return PostResult(ok=False, error="channel_id_missing")

    # Late imports to avoid circular deps and keep scheduler lightweight
    from app.bot.sender import safe_send_message
    from app.content.generator import generate_post
    from app.storage import EventsRepo, PostsRepo, get_session_factory

    today = datetime.now(timezone.utc).date()
    hypothesis_id = _make_hypothesis_id(today, slot_index)
    variant_id = _make_variant_id()

    session_factory = get_session_factory()

    try:
        # --- Determine format ---
        async with session_factory() as session:
            posts_repo = PostsRepo(session)
            today_posts = await posts_repo.list_recent_posts(days=1, limit=50)
            # Filter to actual today
            today_posts = [
                p
                for p in today_posts
                if p.published_at
                and p.published_at.date() == today
            ]

        format_id = _pick_format(today_posts)
        logger.info(f"Channel post: picked format={format_id}, slot={slot_index}")

        # --- Generate content ---
        async with session_factory() as session:
            generated = await generate_post(
                session=session,
                format_id=format_id,
                hypothesis_id=hypothesis_id,
                variant_id=variant_id,
            )

        if not generated.text:
            logger.warning(
                f"Content generation returned empty text for {format_id}"
            )
            return PostResult(ok=False, format_id=format_id, error="empty_content")

        # --- Send to channel ---
        from app.bot.instance import bot

        channel_id = config.channel_id
        # Support both numeric ID and @username
        chat_id: int | str
        try:
            chat_id = int(channel_id)
        except ValueError:
            chat_id = channel_id if channel_id.startswith("@") else f"@{channel_id}"

        msg = await safe_send_message(bot=bot, chat_id=chat_id, text=generated.text)

        if msg is None:
            logger.error("Failed to send channel post via Telegram")
            return PostResult(ok=False, format_id=format_id, error="send_failed")

        telegram_message_id = str(msg.message_id)

        # --- Persist to DB ---
        async with session_factory() as session:
            posts_repo = PostsRepo(session)
            await posts_repo.create_post(
                post_id=telegram_message_id,
                format_id=format_id,
                hypothesis_id=hypothesis_id,
                variant_id=variant_id,
                text=generated.text,
                meta_json=generated.meta_json,
            )

            events_repo = EventsRepo(session)
            await events_repo.log_event(
                event_name="post_published",
                post_id=telegram_message_id,
                payload={
                    "format_id": format_id,
                    "hypothesis_id": hypothesis_id,
                    "variant_id": variant_id,
                    "slot_index": slot_index,
                    "used_llm": generated.used_llm,
                    "lint_passed": generated.lint_passed,
                },
            )

        logger.info(
            f"Channel post published: msg_id={telegram_message_id}, "
            f"format={format_id}"
        )

        return PostResult(
            ok=True,
            post_id=telegram_message_id,
            format_id=format_id,
        )

    except Exception as e:
        logger.exception(f"Channel posting job failed: {e}")
        return PostResult(ok=False, error=str(e)[:200])
