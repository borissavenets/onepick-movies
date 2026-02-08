"""Safe message sending utilities with retry logic."""

import asyncio
from typing import Any

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message

from app.logging import get_logger

logger = get_logger(__name__)

MAX_RETRIES = 3


async def safe_send_message(
    bot: Bot | None,
    chat_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    **kwargs: Any,
) -> Message | None:
    """Send a message with retry logic for rate limits.

    Implements exponential backoff for Telegram rate limits (429 errors).
    Max 3 retries before giving up.

    Args:
        bot: The aiogram Bot instance
        chat_id: Target chat ID
        text: Message text to send
        reply_markup: Optional inline keyboard
        **kwargs: Additional arguments passed to send_message

    Returns:
        The sent Message object, or None if sending failed
    """
    if bot is None:
        logger.error("Bot instance is None, cannot send message")
        return None

    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                **kwargs,
            )

        except TelegramRetryAfter as e:
            retry_after = e.retry_after
            logger.warning(
                f"Rate limited sending to {chat_id}, "
                f"retry after {retry_after}s (attempt {attempt + 1}/{MAX_RETRIES})"
            )

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(retry_after)
            else:
                last_error = e

        except TelegramServerError as e:
            logger.warning(
                f"Telegram server error sending to {chat_id}: {e} "
                f"(attempt {attempt + 1}/{MAX_RETRIES})"
            )

            if attempt < MAX_RETRIES - 1:
                # Exponential backoff for server errors
                await asyncio.sleep(2 ** attempt)
            else:
                last_error = e

        except TelegramForbiddenError:
            logger.info(f"User {chat_id} has blocked the bot or chat is unavailable")
            return None

        except TelegramBadRequest as e:
            logger.error(f"Bad request sending to {chat_id}: {e}")
            return None

        except Exception as e:
            logger.exception(f"Unexpected error sending message to {chat_id}: {e}")
            return None

    if last_error:
        logger.error(
            f"Failed to send message to {chat_id} after {MAX_RETRIES} attempts: {last_error}"
        )

    return None


async def safe_answer_callback(
    callback_query,
    text: str | None = None,
    show_alert: bool = False,
) -> bool:
    """Safely answer a callback query.

    Args:
        callback_query: The callback query to answer
        text: Optional notification text
        show_alert: Whether to show as alert popup

    Returns:
        True if answered successfully, False otherwise
    """
    try:
        await callback_query.answer(text=text, show_alert=show_alert)
        return True
    except Exception as e:
        logger.warning(f"Failed to answer callback: {e}")
        return False


async def safe_send_photo(
    bot: Bot | None,
    chat_id: int,
    photo: str,
    caption: str | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
    **kwargs: Any,
) -> Message | None:
    """Send a photo with retry logic.

    Args:
        bot: The aiogram Bot instance
        chat_id: Target chat ID
        photo: Photo file ID, URL, or local file path
        caption: Optional caption text
        reply_markup: Optional inline keyboard
        **kwargs: Additional arguments passed to send_photo

    Returns:
        The sent Message object, or None if sending failed
    """
    if bot is None:
        logger.error("Bot instance is None, cannot send photo")
        return None

    # Convert local file path to FSInputFile
    import os

    photo_input: str | FSInputFile = photo
    if os.path.isfile(photo):
        photo_input = FSInputFile(photo)

    for attempt in range(MAX_RETRIES):
        try:
            return await bot.send_photo(
                chat_id=chat_id,
                photo=photo_input,
                caption=caption,
                reply_markup=reply_markup,
                **kwargs,
            )

        except TelegramRetryAfter as e:
            logger.warning(
                f"Rate limited sending photo to {chat_id}, "
                f"retry after {e.retry_after}s"
            )

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(e.retry_after)

        except TelegramForbiddenError:
            logger.info(f"User {chat_id} has blocked the bot")
            return None

        except TelegramBadRequest as e:
            logger.error(f"Bad request sending photo to {chat_id}: {e}")
            return None

        except Exception as e:
            logger.exception(f"Unexpected error sending photo to {chat_id}: {e}")
            return None

    return None
