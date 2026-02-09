"""Inline keyboard builders with compact callback data (Ukrainian)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Callback data prefixes:
# s: state selection (light/heavy/escape)
# p: pace selection (slow/fast)
# f: format selection (movie/series)
# a: action on recommendation (hit/another/miss/fav/share/seen)
# r: miss reason (tooslow/tooheavy/notvibe)
# n: navigation (pick/done/restart)


def kb_start() -> InlineKeyboardMarkup:
    """Start flow keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Підібрати зараз", callback_data="n:pick")],
            [
                InlineKeyboardButton(text="⭐ Обране", callback_data="n:favorites"),
                InlineKeyboardButton(text="📜 Історія", callback_data="n:history"),
            ],
            [
                InlineKeyboardButton(text="❓ Допомога", callback_data="n:help"),
                InlineKeyboardButton(text="ℹ️ TMDB", callback_data="n:credits"),
            ],
        ]
    )


def kb_state() -> InlineKeyboardMarkup:
    """State/vibe selection keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Щось легке", callback_data="s:light"),
                InlineKeyboardButton(text="Щось глибоке", callback_data="s:heavy"),
            ],
            [
                InlineKeyboardButton(text="Вимкнути голову", callback_data="s:escape"),
            ],
        ]
    )


def kb_pace(state: str) -> InlineKeyboardMarkup:
    """Pace selection keyboard with encoded state.

    Args:
        state: Previously selected state value

    Returns:
        Keyboard with state encoded in callback
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Повільно", callback_data=f"p:slow|{state}"),
                InlineKeyboardButton(text="Динамічно", callback_data=f"p:fast|{state}"),
            ]
        ]
    )


def kb_format(state: str, pace: str) -> InlineKeyboardMarkup:
    """Format selection keyboard with encoded state and pace.

    Args:
        state: Previously selected state
        pace: Previously selected pace

    Returns:
        Keyboard with state and pace encoded
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Фільм", callback_data=f"f:movie|{state}|{pace}"),
                InlineKeyboardButton(text="Серіал", callback_data=f"f:series|{state}|{pace}"),
            ]
        ]
    )


def kb_recommendation(rec_id: str) -> InlineKeyboardMarkup:
    """Recommendation action keyboard.

    Args:
        rec_id: Recommendation ID (truncated for callback)

    Returns:
        Action keyboard
    """
    # Truncate rec_id to fit callback data limits (64 bytes max)
    short_id = rec_id[:8] if len(rec_id) > 8 else rec_id

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Влучив", callback_data=f"a:hit|{short_id}"),
                InlineKeyboardButton(text="🔁 Ще", callback_data=f"a:another|{short_id}"),
                InlineKeyboardButton(text="❌ Мимо", callback_data=f"a:miss|{short_id}"),
            ],
            [
                InlineKeyboardButton(text="⭐ В обране", callback_data=f"a:fav|{short_id}"),
                InlineKeyboardButton(text="📤 Поділитись", callback_data=f"a:share|{short_id}"),
            ],
            [
                InlineKeyboardButton(text="👁 Вже дивився", callback_data=f"a:seen|{short_id}"),
            ],
        ]
    )


def kb_miss_reason(rec_id: str) -> InlineKeyboardMarkup:
    """Miss reason selection keyboard.

    Args:
        rec_id: Recommendation ID

    Returns:
        Reason selection keyboard
    """
    short_id = rec_id[:8] if len(rec_id) > 8 else rec_id

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Занадто повільно",
                    callback_data=f"r:tooslow|{short_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Занадто важко",
                    callback_data=f"r:tooheavy|{short_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Не моя тема",
                    callback_data=f"r:notvibe|{short_id}"
                ),
            ],
        ]
    )


def kb_after_hit() -> InlineKeyboardMarkup:
    """Keyboard shown after positive feedback."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Ще одну", callback_data="n:another"),
                InlineKeyboardButton(text="Досить", callback_data="n:done"),
            ]
        ]
    )


def kb_restart() -> InlineKeyboardMarkup:
    """Restart flow keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Почати знову", callback_data="n:pick")]
        ]
    )


# Parsing utilities

def parse_callback(data: str) -> tuple[str, str, list[str]]:
    """Parse callback data into prefix, value, and extra params.

    Args:
        data: Raw callback data string

    Returns:
        Tuple of (prefix, value, extra_params)

    Examples:
        "s:light" -> ("s", "light", [])
        "p:slow|escape" -> ("p", "slow", ["escape"])
        "f:movie|escape|slow" -> ("f", "movie", ["escape", "slow"])
    """
    if ":" not in data:
        return ("", data, [])

    prefix, rest = data.split(":", 1)
    parts = rest.split("|")
    value = parts[0]
    extra = parts[1:] if len(parts) > 1 else []

    return (prefix, value, extra)


def encode_answers(state: str, pace: str, format_: str) -> str:
    """Encode answers for storage/callback.

    Args:
        state: State value
        pace: Pace value
        format_: Format value

    Returns:
        Encoded string
    """
    return f"{state}|{pace}|{format_}"


def decode_answers(encoded: str) -> dict[str, str]:
    """Decode answers from encoded string.

    Args:
        encoded: Encoded answers string

    Returns:
        Dictionary with state, pace, format keys
    """
    parts = encoded.split("|")
    if len(parts) >= 3:
        return {
            "state": parts[0],
            "pace": parts[1],
            "format": parts[2],
        }
    return {}
