"""Handlers for the main question flow and recommendation display."""

from aiogram import F, Router
from aiogram.types import CallbackQuery

import json

from app.bot.keyboards import (
    kb_format,
    kb_pace,
    kb_recommendation,
    kb_restart,
    kb_start,
    kb_state,
    parse_callback,
)
from app.bot.messages import (
    CREDITS_MESSAGE,
    HELP_MESSAGE,
    favorites_empty,
    favorites_header,
    favorites_item,
    flow_expired,
    history_empty,
    history_header,
    history_item,
    question_format,
    question_pace,
    question_state,
    recommendation_message,
)
from app.bot.sender import safe_answer_callback, safe_send_message, safe_send_photo
from app.content.style_lint import proofread
from app.bot.session import flow_sessions, rec_sessions
from app.core import get_recommendation
from app.logging import get_logger
from app.storage import EventsRepo, FavoritesRepo, FeedbackRepo, RecsRepo, get_session_factory

router = Router(name="flow")
logger = get_logger(__name__)


@router.callback_query(F.data == "n:pick")
async def handle_pick_now(callback: CallbackQuery) -> None:
    """Handle 'Pick now' button - start the question flow."""
    await safe_answer_callback(callback)

    if not callback.message or not callback.from_user:
        return

    user_id = str(callback.from_user.id)

    # Reset flow session for new flow
    flow_sessions.reset_flow(user_id)

    # Send first question
    await safe_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text=question_state(),
        reply_markup=kb_state(),
    )


@router.callback_query(F.data.startswith("s:"))
async def handle_state_selection(callback: CallbackQuery) -> None:
    """Handle state/vibe selection (Q1)."""
    await safe_answer_callback(callback)

    if not callback.message or not callback.from_user or not callback.data:
        return

    user_id = str(callback.from_user.id)

    # Parse callback
    _, state, _ = parse_callback(callback.data)

    if state not in ("light", "heavy", "escape"):
        logger.warning(f"Invalid state value: {state}")
        await _restart_flow(callback)
        return

    # Store state in session
    session = flow_sessions.get_or_create(user_id)
    session.answers["state"] = state

    logger.info(f"User {user_id} selected state: {state}")

    # Send pace question with state encoded
    await safe_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text=question_pace(),
        reply_markup=kb_pace(state),
    )


@router.callback_query(F.data.startswith("p:"))
async def handle_pace_selection(callback: CallbackQuery) -> None:
    """Handle pace selection (Q2)."""
    await safe_answer_callback(callback)

    if not callback.message or not callback.from_user or not callback.data:
        return

    user_id = str(callback.from_user.id)

    # Parse callback: p:slow|state or p:fast|state
    _, pace, extra = parse_callback(callback.data)

    if pace not in ("slow", "fast"):
        logger.warning(f"Invalid pace value: {pace}")
        await _restart_flow(callback)
        return

    # Get state from callback or session
    state = extra[0] if extra else None
    if not state:
        session = flow_sessions.get(user_id)
        state = session.answers.get("state") if session else None

    if not state:
        logger.warning(f"No state found for user {user_id}, restarting flow")
        await _restart_flow(callback)
        return

    # Store pace in session
    session = flow_sessions.get_or_create(user_id)
    session.answers["state"] = state
    session.answers["pace"] = pace

    logger.info(f"User {user_id} selected pace: {pace}")

    # Send format question with state and pace encoded
    await safe_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text=question_format(),
        reply_markup=kb_format(state, pace),
    )


@router.callback_query(F.data.startswith("f:"))
async def handle_format_selection(callback: CallbackQuery) -> None:
    """Handle format selection (Q3) - finalize and get recommendation."""
    await safe_answer_callback(callback)

    if not callback.message or not callback.from_user or not callback.data:
        return

    user_id = str(callback.from_user.id)

    # Parse callback: f:movie|state|pace or f:series|state|pace
    _, format_choice, extra = parse_callback(callback.data)

    if format_choice not in ("movie", "series"):
        logger.warning(f"Invalid format value: {format_choice}")
        await _restart_flow(callback)
        return

    # Get state and pace from callback or session
    state = extra[0] if len(extra) > 0 else None
    pace = extra[1] if len(extra) > 1 else None

    if not state or not pace:
        session = flow_sessions.get(user_id)
        if session:
            state = state or session.answers.get("state")
            pace = pace or session.answers.get("pace")

    if not state or not pace:
        logger.warning(f"Missing state/pace for user {user_id}, restarting flow")
        await _restart_flow(callback)
        return

    # Finalize answers
    answers = {
        "state": state,
        "pace": pace,
        "format": format_choice,
    }

    # Store in session
    session = flow_sessions.get_or_create(user_id)
    session.answers = answers

    logger.info(f"User {user_id} completed flow: {answers}")

    # Get ref info if available
    ref_info = flow_sessions.get_ref(user_id)

    session_factory = get_session_factory()
    async with session_factory() as db_session:
        events_repo = EventsRepo(db_session)

        # Log answers submitted
        payload = {**answers}
        if ref_info:
            payload["ref_post_id"] = ref_info.get("post_id")
            payload["ref_variant_id"] = ref_info.get("variant_id")

        await events_repo.log_event(
            event_name="answers_submitted",
            user_id=user_id,
            payload=payload,
        )

        # Get recommendation
        result = await get_recommendation(
            session=db_session,
            user_id=user_id,
            answers=answers,
            mode="normal",
        )

        if not result:
            await safe_send_message(
                bot=callback.bot,
                chat_id=callback.message.chat.id,
                text="На жаль, зараз не знайшов нічого підходящого. Спробуй пізніше!",
                reply_markup=kb_restart(),
            )
            return

        # Store rec info in session
        rec_sessions.set_last_rec(user_id, result.rec_id, result.item_id)

        # Log recommendation shown
        await events_repo.log_event(
            event_name="recommendation_shown",
            user_id=user_id,
            rec_id=result.rec_id,
            payload={
                "item_id": result.item_id,
                "title": result.title,
                "mode": "normal",
                "selector_meta": {},  # Placeholder for future
            },
        )

    # Proofread Ukrainian text fields
    rationale = await proofread(result.rationale)
    when_to_watch = await proofread(result.when_to_watch)

    # Send recommendation with poster if available
    message_text = recommendation_message(
        title=result.title,
        rationale=rationale,
        when_to_watch=when_to_watch,
        rating=result.rating,
    )

    if result.poster_url:
        await safe_send_photo(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            photo=result.poster_url,
            caption=message_text,
            reply_markup=kb_recommendation(result.rec_id),
            parse_mode="HTML",
        )
    else:
        await safe_send_message(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            text=message_text,
            reply_markup=kb_recommendation(result.rec_id),
        )


@router.callback_query(F.data == "n:help")
async def handle_help_btn(callback: CallbackQuery) -> None:
    """Handle 'Help' button from start screen."""
    await safe_answer_callback(callback)
    if not callback.message:
        return
    await safe_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text=HELP_MESSAGE,
        reply_markup=kb_start(),
    )


@router.callback_query(F.data == "n:credits")
async def handle_credits_btn(callback: CallbackQuery) -> None:
    """Handle 'TMDB' button from start screen."""
    await safe_answer_callback(callback)
    if not callback.message:
        return
    await safe_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text=CREDITS_MESSAGE,
        reply_markup=kb_start(),
    )


@router.callback_query(F.data == "n:history")
async def handle_history_btn(callback: CallbackQuery) -> None:
    """Handle 'History' button from start screen."""
    await safe_answer_callback(callback)
    if not callback.message or not callback.from_user:
        return

    user_id = str(callback.from_user.id)

    session_factory = get_session_factory()
    async with session_factory() as db_session:
        recs_repo = RecsRepo(db_session)
        feedback_repo = FeedbackRepo(db_session)
        history = await recs_repo.list_user_history(user_id, limit=10)

        if not history:
            await safe_send_message(
                bot=callback.bot,
                chat_id=callback.message.chat.id,
                text=history_empty(),
                reply_markup=kb_start(),
            )
            return

        lines = [history_header()]
        for i, rec in enumerate(history, 1):
            title = rec.item.title if rec.item else "Unknown"
            feedbacks = await feedback_repo.get_feedback_for_rec(rec.rec_id)
            action = feedbacks[0].action if feedbacks else None
            lines.append(history_item(i, title, action))

        await safe_send_message(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            text="\n".join(lines),
            reply_markup=kb_start(),
        )


@router.callback_query(F.data == "n:favorites")
async def handle_favorites(callback: CallbackQuery) -> None:
    """Handle 'Favorites' button from start screen."""
    await safe_answer_callback(callback)

    if not callback.message or not callback.from_user:
        return

    user_id = str(callback.from_user.id)

    session_factory = get_session_factory()
    async with session_factory() as db_session:
        fav_repo = FavoritesRepo(db_session)
        favorites = await fav_repo.list_favorites(user_id, limit=50)

        if not favorites:
            await safe_send_message(
                bot=callback.bot,
                chat_id=callback.message.chat.id,
                text=favorites_empty(),
                reply_markup=kb_start(),
            )
            return

        lines = [favorites_header()]
        for i, fav in enumerate(favorites, 1):
            title = fav.item.title if fav.item else "Unknown"
            lines.append(favorites_item(i, title))

        await safe_send_message(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            text="\n".join(lines),
            reply_markup=kb_start(),
        )


@router.callback_query(F.data == "n:another")
async def handle_nav_another(callback: CallbackQuery) -> None:
    """Handle 'Pick another' from post-hit navigation."""
    await safe_answer_callback(callback)

    if not callback.message or not callback.from_user:
        return

    user_id = str(callback.from_user.id)

    # Get last answers from session
    session = flow_sessions.get(user_id)
    if not session or not session.answers:
        # No session, restart flow
        await _restart_flow(callback)
        return

    answers = session.answers

    # Get last rec to exclude
    rec_session = rec_sessions.get(user_id)
    exclude_ids = set()
    if rec_session and rec_session.last_item_id:
        exclude_ids.add(rec_session.last_item_id)

    session_factory = get_session_factory()
    async with session_factory() as db_session:
        events_repo = EventsRepo(db_session)

        # Get last context for another-but-different
        last_context = None
        if rec_session and rec_session.last_rec_id:
            recs_repo = RecsRepo(db_session)
            last_rec = await recs_repo.get_rec(rec_session.last_rec_id)
            if last_rec and last_rec.context_json:
                try:
                    last_context = json.loads(last_rec.context_json)
                except json.JSONDecodeError:
                    pass

        # Get new recommendation
        result = await get_recommendation(
            session=db_session,
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
                text="Більше варіантів немає. Повертайся пізніше!",
                reply_markup=kb_restart(),
            )
            return

        # Store rec info
        rec_sessions.set_last_rec(user_id, result.rec_id, result.item_id)

        # Log event
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

    # Proofread Ukrainian text fields
    rationale = await proofread(result.rationale)
    when_to_watch = await proofread(result.when_to_watch)

    # Build message with optional delta explainer
    message_text = recommendation_message(
        title=result.title,
        rationale=rationale,
        when_to_watch=when_to_watch,
        rating=result.rating,
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
            reply_markup=kb_recommendation(result.rec_id),
            parse_mode="HTML",
        )
    else:
        await safe_send_message(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            text=message_text,
            reply_markup=kb_recommendation(result.rec_id),
        )


@router.callback_query(F.data == "n:done")
async def handle_nav_done(callback: CallbackQuery) -> None:
    """Handle 'Done' button - end the flow gracefully."""
    await safe_answer_callback(callback)

    if not callback.message:
        return

    await safe_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text="Гарного перегляду! Повертайся, коли захочеш ще.",
        reply_markup=kb_start(),
    )


async def _restart_flow(callback: CallbackQuery) -> None:
    """Send restart message when flow state is missing."""
    if not callback.message:
        return

    await safe_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text=flow_expired(),
        reply_markup=kb_restart(),
    )
