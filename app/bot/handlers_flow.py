"""Handlers for the main question flow and recommendation display."""

import json

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import (
    kb_format,
    kb_hint,
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
    question_hint,
    question_pace,
    question_state,
    recommendation_message,
)
from app.bot.sender import safe_answer_callback, safe_send_message, safe_send_photo
from app.bot.session import flow_sessions, rec_sessions
from app.content.style_lint import proofread
from app.core import get_recommendation
from app.logging import get_logger
from app.storage import (
    EventsRepo,
    FavoritesRepo,
    FeedbackRepo,
    RecsRepo,
    get_session_factory,
)

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
    """Handle format selection (Q3) - show hint question."""
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

    # Store answers in session
    session = flow_sessions.get_or_create(user_id)
    session.answers = {
        "state": state,
        "pace": pace,
        "format": format_choice,
    }
    session.awaiting_hint = True

    logger.info(f"User {user_id} selected format: {format_choice}, showing hint question")

    # Send hint question (Q4) instead of recommendation
    await safe_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text=question_hint(),
        reply_markup=kb_hint(),
    )


@router.callback_query(F.data == "n:skip_hint")
async def handle_skip_hint(callback: CallbackQuery) -> None:
    """Handle 'Skip' button on hint question - proceed without hint."""
    await safe_answer_callback(callback)

    if not callback.message or not callback.from_user:
        return

    user_id = str(callback.from_user.id)

    session = flow_sessions.get(user_id)
    if not session or not session.answers:
        await _restart_flow(callback)
        return

    session.awaiting_hint = False
    session.hint = None

    logger.info(f"User {user_id} skipped hint")

    await _get_and_send_recommendation(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        user_id=user_id,
    )


async def _is_awaiting_hint(message: Message) -> bool:
    """Filter: only match if user is in awaiting_hint state."""
    if not message.from_user:
        return False
    user_id = str(message.from_user.id)
    session = flow_sessions.get(user_id)
    return bool(session and session.awaiting_hint)


@router.message(F.text, _is_awaiting_hint)
async def handle_hint_text(message: Message) -> None:
    """Handle free-text hint input from user."""
    if not message.from_user or not message.text:
        return

    user_id = str(message.from_user.id)

    session = flow_sessions.get(user_id)
    if not session:
        return

    hint = message.text.strip()
    if len(hint) > 200:
        hint = hint[:200]

    session.hint = hint
    session.awaiting_hint = False

    logger.info(f"User {user_id} provided hint: {hint[:50]}...")

    await _get_and_send_recommendation(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=user_id,
    )


async def _get_and_send_recommendation(
    bot,
    chat_id: int,
    user_id: str,
    mode: str = "normal",
    exclude_item_ids: set[str] | None = None,
    last_context: dict | None = None,
    delta_prefix: str | None = None,
) -> None:
    """Shared logic: get recommendation and send it to user.

    Args:
        bot: Bot instance
        chat_id: Chat ID to send to
        user_id: User ID
        mode: Recommendation mode
        exclude_item_ids: Item IDs to exclude
        last_context: Previous rec context (for "another" mode)
        delta_prefix: Optional text prefix (delta explainer)
    """
    session = flow_sessions.get(user_id)
    if not session or not session.answers:
        await safe_send_message(
            bot=bot,
            chat_id=chat_id,
            text=flow_expired(),
            reply_markup=kb_restart(),
        )
        return

    answers = session.answers.copy()

    # Include hint in answers if present
    if session.hint:
        answers["hint"] = session.hint

    # Get ref info if available
    ref_info = flow_sessions.get_ref(user_id)

    session_factory = get_session_factory()
    async with session_factory() as db_session:
        events_repo = EventsRepo(db_session)

        # Log answers submitted (only for normal mode)
        if mode == "normal":
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
            mode=mode,
            exclude_item_ids=exclude_item_ids,
            last_context=last_context,
        )

        if not result:
            text = (
                "Більше варіантів немає. Повертайся пізніше!"
                if mode == "another"
                else "На жаль, зараз не знайшов нічого підходящого. Спробуй пізніше!"
            )
            await safe_send_message(
                bot=bot,
                chat_id=chat_id,
                text=text,
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
                "mode": mode,
                "selector_meta": {},
            },
        )

    # Proofread Ukrainian text fields
    rationale = await proofread(result.rationale)
    when_to_watch = await proofread(result.when_to_watch)

    # Build message
    message_text = recommendation_message(
        title=result.title,
        rationale=rationale,
        when_to_watch=when_to_watch,
        rating=result.rating,
    )

    # Prepend delta explainer if present
    if delta_prefix:
        message_text = f"<i>{delta_prefix}</i>\n\n{message_text}"
    elif hasattr(result, "delta_explainer") and result.delta_explainer:
        message_text = f"<i>{result.delta_explainer}</i>\n\n{message_text}"

    # Send recommendation with poster if available
    if result.poster_url:
        await safe_send_photo(
            bot=bot,
            chat_id=chat_id,
            photo=result.poster_url,
            caption=message_text,
            reply_markup=kb_recommendation(result.rec_id, result.title, result.meta.get("item_type", "movie")),
            parse_mode="HTML",
        )
    else:
        await safe_send_message(
            bot=bot,
            chat_id=chat_id,
            text=message_text,
            reply_markup=kb_recommendation(result.rec_id, result.title, result.meta.get("item_type", "movie")),
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
        await _restart_flow(callback)
        return

    # Get last rec to exclude
    rec_session = rec_sessions.get(user_id)
    exclude_ids = set()
    if rec_session and rec_session.last_item_id:
        exclude_ids.add(rec_session.last_item_id)

    # Get last context for another-but-different
    last_context = None
    session_factory = get_session_factory()
    async with session_factory() as db_session:
        if rec_session and rec_session.last_rec_id:
            recs_repo = RecsRepo(db_session)
            last_rec = await recs_repo.get_rec(rec_session.last_rec_id)
            if last_rec and last_rec.context_json:
                try:
                    last_context = json.loads(last_rec.context_json)
                except json.JSONDecodeError:
                    pass

    await _get_and_send_recommendation(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        user_id=user_id,
        mode="another",
        exclude_item_ids=exclude_ids,
        last_context=last_context,
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
