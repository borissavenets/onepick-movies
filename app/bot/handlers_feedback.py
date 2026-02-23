"""Handlers for user feedback on recommendations."""

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.keyboards import (
    kb_after_hit,
    kb_miss_reason,
    kb_recommendation,
    kb_restart,
    parse_callback,
)
from app.bot.messages import (
    ack_dismissed,
    ack_favorite,
    ack_hit,
    ack_miss,
    miss_recovery,
    recommendation_message,
    share_snippet,
)
from app.bot.sender import safe_answer_callback, safe_send_message, safe_send_photo
from app.bot.session import flow_sessions, rec_sessions
from app.core import get_recommendation, update_weights
from app.logging import get_logger
from app.storage import DismissedRepo, EventsRepo, FavoritesRepo, FeedbackRepo, RecsRepo, get_session_factory

router = Router(name="feedback")
logger = get_logger(__name__)


def _get_rec_id_from_callback(callback_data: str, user_id: str) -> str | None:
    """Extract rec_id from callback data or session.

    Args:
        callback_data: Raw callback data
        user_id: User ID for session lookup

    Returns:
        Full rec_id or None
    """
    _, _, extra = parse_callback(callback_data)
    short_id = extra[0] if extra else None

    # Get full rec_id from session
    rec_session = rec_sessions.get(user_id)
    if rec_session and rec_session.last_rec_id:
        # Verify short_id matches
        if short_id and rec_session.last_rec_id.startswith(short_id):
            return rec_session.last_rec_id
        # If no short_id or mismatch, still use session rec
        return rec_session.last_rec_id

    return None


@router.callback_query(F.data.startswith("a:hit"))
async def handle_hit(callback: CallbackQuery) -> None:
    """Handle 'Hit' feedback - user liked the recommendation."""
    await safe_answer_callback(callback)

    if not callback.message or not callback.from_user or not callback.data:
        return

    user_id = str(callback.from_user.id)
    rec_id = _get_rec_id_from_callback(callback.data, user_id)

    if not rec_id:
        logger.warning(f"No rec_id found for hit from user {user_id}")
        await _send_no_rec_error(callback)
        return

    logger.info(f"User {user_id} marked rec {rec_id[:8]} as hit")

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Add feedback
        feedback_repo = FeedbackRepo(session)
        await feedback_repo.add_feedback(
            user_id=user_id,
            rec_id=rec_id,
            action="hit",
        )

        # Update weights based on feedback
        await update_weights(session, user_id, rec_id, "hit")

        # Log event
        events_repo = EventsRepo(session)
        await events_repo.log_event(
            event_name="feedback",
            user_id=user_id,
            rec_id=rec_id,
            payload={"action": "hit"},
        )

    # Send acknowledgment with next options
    await safe_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text=ack_hit(),
        reply_markup=kb_after_hit(),
    )


@router.callback_query(F.data.startswith("a:another"))
async def handle_another(callback: CallbackQuery) -> None:
    """Handle 'Another' feedback - user wants a different option."""
    await safe_answer_callback(callback)

    if not callback.message or not callback.from_user or not callback.data:
        return

    user_id = str(callback.from_user.id)
    rec_id = _get_rec_id_from_callback(callback.data, user_id)

    # Get last answers
    flow_session = flow_sessions.get(user_id)
    if not flow_session or not flow_session.answers:
        await _send_restart(callback)
        return

    answers = flow_session.answers.copy()
    if flow_session.hint:
        answers["hint"] = flow_session.hint

    # Get current item to exclude
    rec_session = rec_sessions.get(user_id)
    exclude_ids = set()
    if rec_session and rec_session.last_item_id:
        exclude_ids.add(rec_session.last_item_id)

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Add feedback if we have rec_id
        if rec_id:
            feedback_repo = FeedbackRepo(session)
            await feedback_repo.add_feedback(
                user_id=user_id,
                rec_id=rec_id,
                action="another",
            )

            # Update weights based on feedback
            await update_weights(session, user_id, rec_id, "another")

        events_repo = EventsRepo(session)

        # Log feedback event
        if rec_id:
            await events_repo.log_event(
                event_name="feedback",
                user_id=user_id,
                rec_id=rec_id,
                payload={"action": "another"},
            )

        # Get last context for another-but-different
        last_context = None
        if rec_id:
            recs_repo = RecsRepo(session)
            last_rec = await recs_repo.get_rec(rec_id)
            if last_rec and last_rec.context_json:
                import json
                try:
                    last_context = json.loads(last_rec.context_json)
                except json.JSONDecodeError:
                    pass

        # Get new recommendation
        result = await get_recommendation(
            session=session,
            user_id=user_id,
            answers=answers,
            mode="another",
            exclude_item_ids=exclude_ids,
            last_context=last_context,
        )

        if not result:
            await safe_send_message(
                bot=callback.bot,
                chat_id=callback.message.chat.id,
                text="Це все, що в мене є на зараз. Спробуй пізніше!",
                reply_markup=kb_restart(),
            )
            return

        # Store new rec info
        rec_sessions.set_last_rec(user_id, result.rec_id, result.item_id)

        # Log new recommendation
        await events_repo.log_event(
            event_name="recommendation_shown",
            user_id=user_id,
            rec_id=result.rec_id,
            payload={
                "item_id": result.item_id,
                "title": result.title,
                "mode": "another",
            },
        )

    # Build message with optional delta explainer
    message_text = recommendation_message(
        title=result.title,
        rationale=result.rationale,
        when_to_watch=result.when_to_watch,
        rating=result.rating,
        hint_rationale=result.hint_rationale,
    )

    # Prepend delta explainer if present
    if hasattr(result, "delta_explainer") and result.delta_explainer:
        message_text = f"<i>{result.delta_explainer}</i>\n\n{message_text}"

    # Send new recommendation with poster if available
    if result.poster_url:
        await safe_send_photo(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            photo=result.poster_url,
            caption=message_text,
            reply_markup=kb_recommendation(result.rec_id, result.title, result.meta.get("item_type", "movie")),
            parse_mode="HTML",
        )
    else:
        await safe_send_message(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            text=message_text,
            reply_markup=kb_recommendation(result.rec_id, result.title, result.meta.get("item_type", "movie")),
        )


@router.callback_query(F.data.startswith("a:miss"))
async def handle_miss(callback: CallbackQuery) -> None:
    """Handle 'Miss' feedback - user didn't like the recommendation."""
    await safe_answer_callback(callback)

    if not callback.message or not callback.from_user or not callback.data:
        return

    user_id = str(callback.from_user.id)
    rec_id = _get_rec_id_from_callback(callback.data, user_id)

    if not rec_id:
        logger.warning(f"No rec_id found for miss from user {user_id}")
        await _send_no_rec_error(callback)
        return

    logger.info(f"User {user_id} marked rec {rec_id[:8]} as miss")

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Add feedback
        feedback_repo = FeedbackRepo(session)
        await feedback_repo.add_feedback(
            user_id=user_id,
            rec_id=rec_id,
            action="miss",
        )

        # Update weights based on feedback (miss without reason yet)
        await update_weights(session, user_id, rec_id, "miss")

        # Log event
        events_repo = EventsRepo(session)
        await events_repo.log_event(
            event_name="feedback",
            user_id=user_id,
            rec_id=rec_id,
            payload={"action": "miss"},
        )

    # Ask for miss reason
    await safe_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text=ack_miss(),
        reply_markup=kb_miss_reason(rec_id),
    )


@router.callback_query(F.data.startswith("r:"))
async def handle_miss_reason(callback: CallbackQuery) -> None:
    """Handle miss reason selection."""
    await safe_answer_callback(callback)

    if not callback.message or not callback.from_user or not callback.data:
        return

    user_id = str(callback.from_user.id)

    # Parse reason
    _, reason, extra = parse_callback(callback.data)

    if reason not in ("tooslow", "tooheavy", "notvibe"):
        logger.warning(f"Invalid miss reason: {reason}")
        return

    rec_id = _get_rec_id_from_callback(callback.data, user_id)

    logger.info(f"User {user_id} gave miss reason: {reason}")

    # Get answers for recovery rec
    flow_session = flow_sessions.get(user_id)
    if not flow_session or not flow_session.answers:
        await _send_restart(callback)
        return

    answers = flow_session.answers.copy()
    if flow_session.hint:
        answers["hint"] = flow_session.hint

    # Get current item to exclude
    rec_session = rec_sessions.get(user_id)
    exclude_ids = set()
    if rec_session and rec_session.last_item_id:
        exclude_ids.add(rec_session.last_item_id)

    session_factory = get_session_factory()
    async with session_factory() as session:
        events_repo = EventsRepo(session)

        # Update weights with reason for corrective learning
        if rec_id:
            await update_weights(session, user_id, rec_id, "miss", reason=reason)

        # Log miss reason event
        await events_repo.log_event(
            event_name="miss_reason",
            user_id=user_id,
            rec_id=rec_id,
            payload={"reason": reason},
        )

        # Send "finding better" message
        await safe_send_message(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            text=miss_recovery(),
        )

        # Get recovery recommendation
        result = await get_recommendation(
            session=session,
            user_id=user_id,
            answers=answers,
            mode="miss_recover",
            exclude_item_ids=exclude_ids,
        )

        if not result:
            await safe_send_message(
                bot=callback.bot,
                chat_id=callback.message.chat.id,
                text="На жаль, варіанти закінчились. Спробуй почати спочатку!",
                reply_markup=kb_restart(),
            )
            return

        # Store new rec info
        rec_sessions.set_last_rec(user_id, result.rec_id, result.item_id)

        # Log new recommendation
        await events_repo.log_event(
            event_name="recommendation_shown",
            user_id=user_id,
            rec_id=result.rec_id,
            payload={
                "item_id": result.item_id,
                "title": result.title,
                "mode": "miss_recover",
                "miss_reason": reason,
            },
        )

    # Send recovery recommendation with poster if available
    message_text = recommendation_message(
        title=result.title,
        rationale=result.rationale,
        when_to_watch=result.when_to_watch,
        rating=result.rating,
        hint_rationale=result.hint_rationale,
    )

    if result.poster_url:
        await safe_send_photo(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            photo=result.poster_url,
            caption=message_text,
            reply_markup=kb_recommendation(result.rec_id, result.title, result.meta.get("item_type", "movie")),
            parse_mode="HTML",
        )
    else:
        await safe_send_message(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            text=message_text,
            reply_markup=kb_recommendation(result.rec_id, result.title, result.meta.get("item_type", "movie")),
        )


@router.callback_query(F.data.startswith("a:seen"))
async def handle_seen(callback: CallbackQuery) -> None:
    """Handle 'Already watched' — dismiss item and show next recommendation."""
    await safe_answer_callback(callback)

    if not callback.message or not callback.from_user or not callback.data:
        return

    user_id = str(callback.from_user.id)
    rec_id = _get_rec_id_from_callback(callback.data, user_id)

    # Get item_id from session
    rec_session = rec_sessions.get(user_id)
    if not rec_session or not rec_session.last_item_id:
        logger.warning(f"No item_id found for seen from user {user_id}")
        await _send_no_rec_error(callback)
        return

    item_id = rec_session.last_item_id

    logger.info(f"User {user_id} dismissed item {item_id} (already watched)")

    # Get answers for next recommendation
    flow_session = flow_sessions.get(user_id)
    if not flow_session or not flow_session.answers:
        await _send_restart(callback)
        return

    answers = flow_session.answers.copy()
    if flow_session.hint:
        answers["hint"] = flow_session.hint

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Save dismissed
        dismissed_repo = DismissedRepo(session)
        await dismissed_repo.add_dismissed(user_id, item_id)

        # Add feedback if we have rec_id
        if rec_id:
            feedback_repo = FeedbackRepo(session)
            await feedback_repo.add_feedback(
                user_id=user_id,
                rec_id=rec_id,
                action="dismissed",
            )

        # Log event
        events_repo = EventsRepo(session)
        await events_repo.log_event(
            event_name="feedback",
            user_id=user_id,
            rec_id=rec_id,
            payload={"action": "dismissed", "item_id": item_id},
        )

        # Send confirmation
        await safe_send_message(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            text=ack_dismissed(),
        )

        # Get next recommendation (same flow as handle_another)
        exclude_ids = {item_id}

        result = await get_recommendation(
            session=session,
            user_id=user_id,
            answers=answers,
            mode="another",
            exclude_item_ids=exclude_ids,
        )

        if not result:
            await safe_send_message(
                bot=callback.bot,
                chat_id=callback.message.chat.id,
                text="Це все, що в мене є на зараз. Спробуй пізніше!",
                reply_markup=kb_restart(),
            )
            return

        # Store new rec info
        rec_sessions.set_last_rec(user_id, result.rec_id, result.item_id)

        # Log new recommendation
        await events_repo.log_event(
            event_name="recommendation_shown",
            user_id=user_id,
            rec_id=result.rec_id,
            payload={
                "item_id": result.item_id,
                "title": result.title,
                "mode": "after_dismissed",
            },
        )

    # Send new recommendation
    message_text = recommendation_message(
        title=result.title,
        rationale=result.rationale,
        when_to_watch=result.when_to_watch,
        rating=result.rating,
        hint_rationale=result.hint_rationale,
    )

    if result.poster_url:
        await safe_send_photo(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            photo=result.poster_url,
            caption=message_text,
            reply_markup=kb_recommendation(result.rec_id, result.title, result.meta.get("item_type", "movie")),
            parse_mode="HTML",
        )
    else:
        await safe_send_message(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            text=message_text,
            reply_markup=kb_recommendation(result.rec_id, result.title, result.meta.get("item_type", "movie")),
        )


@router.callback_query(F.data.startswith("a:fav"))
async def handle_favorite(callback: CallbackQuery) -> None:
    """Handle 'Favorite' feedback - user wants to save the item."""
    await safe_answer_callback(callback)

    if not callback.message or not callback.from_user or not callback.data:
        return

    user_id = str(callback.from_user.id)
    rec_id = _get_rec_id_from_callback(callback.data, user_id)

    # Get item_id from session
    rec_session = rec_sessions.get(user_id)
    if not rec_session or not rec_session.last_item_id:
        logger.warning(f"No item_id found for favorite from user {user_id}")
        await _send_no_rec_error(callback)
        return

    item_id = rec_session.last_item_id

    logger.info(f"User {user_id} favorited item {item_id}")

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Add to favorites
        favorites_repo = FavoritesRepo(session)
        await favorites_repo.add_favorite(user_id, item_id)

        # Add feedback if we have rec_id
        if rec_id:
            feedback_repo = FeedbackRepo(session)
            await feedback_repo.add_feedback(
                user_id=user_id,
                rec_id=rec_id,
                action="favorite",
            )

            # Update weights based on feedback
            await update_weights(session, user_id, rec_id, "favorite")

        # Log event
        events_repo = EventsRepo(session)
        await events_repo.log_event(
            event_name="feedback",
            user_id=user_id,
            rec_id=rec_id,
            payload={"action": "favorite", "item_id": item_id},
        )

    # Send confirmation
    await safe_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text=ack_favorite(),
    )


@router.callback_query(F.data.startswith("a:share"))
async def handle_share(callback: CallbackQuery) -> None:
    """Handle 'Share' feedback - user wants to share the recommendation."""
    await safe_answer_callback(callback)

    if not callback.message or not callback.from_user or not callback.data:
        return

    user_id = str(callback.from_user.id)
    rec_id = _get_rec_id_from_callback(callback.data, user_id)

    # Get item info from session
    rec_session = rec_sessions.get(user_id)
    if not rec_session or not rec_session.last_item_id:
        logger.warning(f"No item_id found for share from user {user_id}")
        await _send_no_rec_error(callback)
        return

    item_id = rec_session.last_item_id

    logger.info(f"User {user_id} shared item {item_id}")

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Add feedback if we have rec_id
        if rec_id:
            feedback_repo = FeedbackRepo(session)
            await feedback_repo.add_feedback(
                user_id=user_id,
                rec_id=rec_id,
                action="share",
            )

            # Update weights based on feedback
            await update_weights(session, user_id, rec_id, "share")

        # Log event
        events_repo = EventsRepo(session)
        await events_repo.log_event(
            event_name="share_clicked",
            user_id=user_id,
            rec_id=rec_id,
            payload={"item_id": item_id},
        )

        # Get item title from items repo
        from app.storage import ItemsRepo
        items_repo = ItemsRepo(session)
        item = await items_repo.get_item(item_id)
        title = item.title if item else "a great pick"

    # Get bot username
    bot_info = await callback.bot.get_me()
    bot_username = bot_info.username or "onepick_movies_bot"

    # Send shareable snippet
    await safe_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text=share_snippet(title, bot_username),
    )


async def _send_no_rec_error(callback: CallbackQuery) -> None:
    """Send error when no recommendation context is available."""
    if not callback.message:
        return

    await safe_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text="Втратив контекст останньої рекомендації. Давай спочатку!",
        reply_markup=kb_restart(),
    )


async def _send_restart(callback: CallbackQuery) -> None:
    """Send restart prompt."""
    if not callback.message:
        return

    await safe_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text="Давай почнемо спочатку — тисни кнопку нижче.",
        reply_markup=kb_restart(),
    )
