"""Handle reaction count updates from channel posts."""

from aiogram import Router
from aiogram.types import MessageReactionCountUpdated

from app.logging import get_logger

logger = get_logger(__name__)

router = Router(name="reactions")


@router.message_reaction_count()
async def on_reaction_count(event: MessageReactionCountUpdated) -> None:
    """Track reaction counts on channel posts.

    Telegram sends this update when reactions change on a channel message.
    We sum all reaction counts and update the latest PostMetric snapshot.
    """
    from app.storage import MetricsRepo, PostsRepo, get_session_factory

    tg_msg_id = str(event.message_id)
    chat_id = event.chat.id

    # Sum all reaction types
    total_reactions = sum(r.total_count for r in event.reactions)

    logger.info(
        f"Reaction update: chat={chat_id}, msg={tg_msg_id}, "
        f"total_reactions={total_reactions}"
    )

    session_factory = get_session_factory()

    async with session_factory() as session:
        # Find post by telegram message ID
        posts_repo = PostsRepo(session)
        post = await posts_repo.find_by_telegram_message_id(tg_msg_id)

        if not post:
            logger.debug(f"No post found for tg_msg_id={tg_msg_id}, skipping")
            return

        # Update or create metrics snapshot with reaction count
        metrics_repo = MetricsRepo(session)
        existing = await metrics_repo.get_latest_snapshot(post.post_id)

        if existing:
            # Update existing snapshot's reactions
            from sqlalchemy import update
            from app.storage.models import PostMetric

            stmt = (
                update(PostMetric)
                .where(PostMetric.id == existing.id)
                .values(reactions=total_reactions)
            )
            await session.execute(stmt)
            await session.commit()
            logger.info(
                f"Updated reactions for post {post.post_id}: {total_reactions}"
            )
        else:
            # Create new snapshot with just reactions
            await metrics_repo.insert_snapshot(
                post_id=post.post_id,
                reactions=total_reactions,
            )
            logger.info(
                f"Created metrics snapshot for post {post.post_id}: "
                f"reactions={total_reactions}"
            )
