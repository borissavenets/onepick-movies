"""Publish posts to the Telegram channel.

Bandit-lite format selection (70 % exploit / 30 % explore) and simple A/B
variant alternation.  Schedule bandit picks the active posting schedule
and gates execution per slot.  Deep-link, hypothesis_id, variant_id, and
schedule_id are always written to ``meta_json``.
"""

import json
import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.config import config
from app.logging import get_logger

logger = get_logger(__name__)

ALL_FORMATS: list[str] = [
    "one_pick_emotion",
    "if_liked_x_then_y",
    "fact_then_pick",
    "poll",
    "bot_teaser",
    "mood_trio",
    "versus",
    "quote_hook",
]

EXPLOIT_RATE = 0.70


@dataclass
class PostResult:
    """Outcome of a single channel-post attempt."""

    ok: bool
    post_id: str | None = None
    format_id: str | None = None
    error: str | None = None


# ------------------------------------------------------------------
# Format selection – bandit-lite
# ------------------------------------------------------------------

async def _avg_scores_by_format(session, days: int = 14) -> dict[str, float]:
    """Return average *scored* post_score per format_id over the last N days."""
    from sqlalchemy import func, select
    from app.storage.models import Post, PostMetric

    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(Post.format_id, func.avg(PostMetric.score))
        .join(PostMetric, PostMetric.post_id == Post.post_id)
        .where(Post.published_at >= since, PostMetric.score.is_not(None))
        .group_by(Post.format_id)
    )
    result = await session.execute(stmt)
    return {row[0]: float(row[1]) for row in result.all()}


async def _pick_format_bandit(session, last_format: str | None = None) -> str:
    """70 % exploit best avg score, 30 % explore random other format.

    Avoids picking the same format as the previous post.
    """
    scores = await _avg_scores_by_format(session)

    available = [f for f in ALL_FORMATS if f != last_format] if last_format else ALL_FORMATS

    if not scores:
        return random.choice(available)

    if random.random() < EXPLOIT_RATE:
        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        return best if best != last_format else random.choice(available)

    # Explore: pick from formats that are NOT the current best
    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    others = [f for f in available if f != best]
    return random.choice(others) if others else random.choice(available)


# ------------------------------------------------------------------
# A/B helpers
# ------------------------------------------------------------------

def _make_hypothesis_id(today: date, slot_index: int) -> str:
    return f"h-{today.isoformat()}-{slot_index}"


def _choose_variant(today_posts: list) -> str:
    """Alternate v-a / v-b based on count of today's posts."""
    return "v-b" if len(today_posts) % 2 == 1 else "v-a"


def _build_deeplink(post_id: str, variant_id: str) -> str:
    return f"https://t.me/{config.bot_username}?start=post_{post_id}_{variant_id}"


def _parse_channel_id(raw: str) -> int | str:
    """Convert env value to chat_id usable by Telegram API."""
    try:
        return int(raw)
    except ValueError:
        return raw if raw.startswith("@") else f"@{raw}"


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------

async def run_publish_post(
    slot_index: int = 0,
    slot_time: str | None = None,
) -> PostResult:
    """Generate, publish, and persist one channel post.

    Args:
        slot_index: Time-slot ordinal that triggered this invocation.
        slot_time: The time string (e.g. "19:30") of this slot.
                   Used by the schedule bandit to gate execution.

    Returns:
        PostResult with outcome details.
    """
    if not config.channel_post_enabled:
        logger.info("Channel posting disabled, skipping")
        return PostResult(ok=False, error="posting_disabled")

    if not config.channel_id:
        logger.warning("CHANNEL_ID not set, skipping channel post")
        return PostResult(ok=False, error="channel_id_missing")

    from app.bot.sender import safe_send_message
    from app.content.generator import generate_post
    from app.jobs.schedule_presets import pick_schedule_bandit, slot_in_schedule
    from app.storage import (
        ABWinnersRepo,
        EventsRepo,
        PostsRepo,
        get_session_factory,
    )

    today = datetime.now(timezone.utc).date()
    hypothesis_id = _make_hypothesis_id(today, slot_index)
    post_uuid = str(uuid.uuid4())

    session_factory = get_session_factory()

    try:
        # --- Schedule bandit: decide if this slot should fire ---
        schedule_id: str | None = None
        if slot_time and slot_time != "interval":
            async with session_factory() as session:
                schedule_id = await pick_schedule_bandit(session)

                # Log the bandit pick
                events_repo = EventsRepo(session)
                await events_repo.log_event(
                    event_name="schedule_bandit_pick",
                    payload={
                        "schedule_id": schedule_id,
                        "slot_time": slot_time,
                        "slot_index": slot_index,
                    },
                )

            if not slot_in_schedule(slot_time, schedule_id):
                logger.info(
                    f"Slot {slot_time} not in active schedule "
                    f"'{schedule_id}', skipping"
                )
                return PostResult(ok=False, error="slot_not_in_schedule")

        # --- Determine today's posts & variant ---
        async with session_factory() as session:
            posts_repo = PostsRepo(session)
            today_posts = await posts_repo.list_recent_posts(days=1, limit=50)
            today_posts = [
                p for p in today_posts
                if p.published_at and p.published_at.date() == today
            ]

            # Check for active A/B winner
            ab_repo = ABWinnersRepo(session)
            winner = await ab_repo.get_active_winner(hypothesis_id)
            variant_id = winner.winner_variant_id if winner else _choose_variant(today_posts)

            # --- Bandit-lite format selection (avoid repeat) ---
            last_format = None
            if today_posts:
                import json as _json
                try:
                    meta = _json.loads(today_posts[0].meta_json) if today_posts[0].meta_json else {}
                    last_format = meta.get("format_id") or today_posts[0].format_id
                except (ValueError, TypeError):
                    last_format = today_posts[0].format_id
            format_id = await _pick_format_bandit(session, last_format=last_format)

        logger.info(
            f"Publishing: format={format_id}, variant={variant_id}, "
            f"slot={slot_index}, schedule={schedule_id}"
        )

        deeplink = _build_deeplink(post_uuid, variant_id)

        # --- Generate content ---
        async with session_factory() as session:
            generated = await generate_post(
                session=session,
                format_id=format_id,
                hypothesis_id=hypothesis_id,
                variant_id=variant_id,
                bot_deeplink_url=deeplink,
            )

        if not generated.text:
            logger.warning(f"Content generation returned empty text for {format_id}")
            return PostResult(ok=False, format_id=format_id, error="empty_content")

        # --- Enrich meta_json with deeplink & ids ---
        try:
            meta = json.loads(generated.meta_json)
        except (json.JSONDecodeError, TypeError):
            meta = {}
        meta["deeplink"] = deeplink
        meta["hypothesis_id"] = hypothesis_id
        meta["variant_id"] = variant_id
        if schedule_id:
            meta["schedule_id"] = schedule_id
        enriched_meta = json.dumps(meta, ensure_ascii=False)

        # --- Persist to DB FIRST (before sending to Telegram) ---
        # This ensures the items are recorded for dedup even if the send
        # step partially fails or overlaps with another publish call.
        async with session_factory() as session:
            posts_repo = PostsRepo(session)
            await posts_repo.create_post(
                post_id=post_uuid,
                format_id=format_id,
                hypothesis_id=hypothesis_id,
                variant_id=variant_id,
                text=generated.text,
                meta_json=enriched_meta,
            )

        # --- Send to channel ---
        from app.bot.instance import bot

        chat_id = _parse_channel_id(config.channel_id)

        if generated.poster_url:
            from app.bot.sender import safe_send_photo

            msg = await safe_send_photo(
                bot=bot,
                chat_id=chat_id,
                photo=generated.poster_url,
                caption=generated.text,
            )
        else:
            msg = await safe_send_message(
                bot=bot,
                chat_id=chat_id,
                text=generated.text,
                disable_web_page_preview=True,
            )

        if msg is None:
            logger.error("Failed to send channel post via Telegram, removing DB record")
            # Remove the pre-persisted record so it doesn't block future selection
            async with session_factory() as session:
                posts_repo = PostsRepo(session)
                await posts_repo.delete_post(post_uuid)
            return PostResult(ok=False, format_id=format_id, error="send_failed")

        telegram_message_id = str(msg.message_id)

        # --- Update DB record with telegram_message_id ---
        meta["telegram_message_id"] = telegram_message_id
        enriched_meta = json.dumps(meta, ensure_ascii=False)

        async with session_factory() as session:
            posts_repo = PostsRepo(session)
            await posts_repo.update_post_meta(post_uuid, enriched_meta)

            events_repo = EventsRepo(session)
            await events_repo.log_event(
                event_name="post_published",
                post_id=post_uuid,
                payload={
                    "format_id": format_id,
                    "hypothesis_id": hypothesis_id,
                    "variant_id": variant_id,
                    "schedule_id": schedule_id,
                    "scheduled_slot": slot_index,
                    "slot_time": slot_time,
                    "telegram_message_id": telegram_message_id,
                    "used_llm": generated.used_llm,
                    "lint_passed": generated.lint_passed,
                },
            )

        logger.info(
            f"Post published: id={post_uuid}, tg_msg={telegram_message_id}, "
            f"format={format_id}, variant={variant_id}, schedule={schedule_id}"
        )

        return PostResult(ok=True, post_id=post_uuid, format_id=format_id)

    except Exception as e:
        logger.exception(f"Publish post job failed: {e}")
        return PostResult(ok=False, error=str(e)[:200])
