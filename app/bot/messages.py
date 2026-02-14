"""Message templates and text constants (Ukrainian)."""


def start_message() -> str:
    """Welcome message with value proposition."""
    return (
        "<b>Привіт! Підберу фільм чи серіал під твій настрій.</b>\n\n"
        "3 швидкі питання — одна точна рекомендація.\n\n"
        "Тисни нижче, щоб почати."
    )


def question_state() -> str:
    """First question: emotional state."""
    return (
        "<b>Який у тебе зараз настрій?</b>\n\n"
        "Обери те, що найбільше відгукується прямо зараз:"
    )


def question_pace() -> str:
    """Second question: desired pace."""
    return (
        "<b>Який темп тобі зараз підходить?</b>\n\n"
        "Повільно і вдумливо — чи швидко і динамічно?"
    )


def question_format() -> str:
    """Third question: content format."""
    return (
        "<b>Фільм чи серіал — що тобі ближче?</b>\n\n"
        "Одна завершена історія чи тривала подорож?"
    )


def question_hint() -> str:
    """Fourth question: optional free-text hint for better matching."""
    return (
        "<b>Є побажання?</b>\n\n"
        "Напиши, що хочеш побачити. Наприклад:\n"
        "- щось схоже на Бетмена\n"
        "- класний детектив\n"
        "- корейська драма\n"
        "- з гарним саундтреком\n\n"
        "Або натисни <b>Пропустити</b>, щоб я підібрав сам."
    )


def recommendation_message(
    title: str,
    rationale: str,
    when_to_watch: str,
    rating: float | None = None,
) -> str:
    """Recommendation card message.

    Args:
        title: Content title
        rationale: Why this matches (max ~320 chars)
        when_to_watch: Viewing context suggestion
        rating: TMDB rating (0-10)

    Returns:
        Formatted recommendation message
    """
    rating_str = f"⭐ {rating:.1f}" if rating else ""
    title_line = f"<b>{title}</b>  {rating_str}" if rating_str else f"<b>{title}</b>"

    return (
        f"{title_line}\n\n"
        f"{rationale}\n\n"
        f"<i>{when_to_watch}</i>"
    )


def ack_hit() -> str:
    """Acknowledgment for positive feedback."""
    return (
        "Чудово! Радий, що влучив.\n\n"
        "Хочеш ще одну рекомендацію чи на сьогодні досить?"
    )


def ack_miss() -> str:
    """Acknowledgment when user says it's not a match."""
    return "Зрозумів. Швидке питання — що не зайшло?"


def ack_another() -> str:
    """Acknowledgment when user wants another option."""
    return "Вже шукаю..."


def ack_favorite() -> str:
    """Confirmation when item added to favorites."""
    return "Збережено в обране."


def ack_dismissed() -> str:
    """Confirmation when item marked as already watched."""
    return "Зрозумів, більше не пропонуватиму."


def ack_share() -> str:
    """Message with shareable content."""
    return "Ось посилання для друзів:"


def share_snippet(title: str, bot_username: str) -> str:
    """Shareable text snippet.

    Args:
        title: Content title
        bot_username: Bot's username for deep-link

    Returns:
        Formatted share text
    """
    return (
        f"Глянь \"{title}\" — знайшов через @{bot_username}\n\n"
        f"Підбери собі: https://t.me/{bot_username}"
    )


def reset_done() -> str:
    """Confirmation that preferences were reset."""
    return (
        "Готово! Твої вподобання скинуто.\n\n"
        "Почнемо спочатку? Тисни /start"
    )


def history_header() -> str:
    """Header for history list."""
    return "<b>Твої останні рекомендації:</b>\n"


def history_item(index: int, title: str, action: str | None) -> str:
    """Format single history item.

    Args:
        index: Item number (1-based)
        title: Content title
        action: Last feedback action or None

    Returns:
        Formatted history line
    """
    status = ""
    if action == "hit":
        status = " ✅"
    elif action == "miss":
        status = " ❌"
    elif action == "favorite":
        status = " ⭐"

    return f"{index}. {title}{status}"


def history_empty() -> str:
    """Message when no history exists."""
    return "Ще нема рекомендацій. Тисни /start щоб отримати першу!"


def favorites_header() -> str:
    """Header for favorites list."""
    return "<b>Твоє обране:</b>\n"


def favorites_item(index: int, title: str) -> str:
    """Format single favorite item.

    Args:
        index: Item number (1-based)
        title: Content title

    Returns:
        Formatted favorite line
    """
    return f"{index}. ⭐ {title}"


def favorites_empty() -> str:
    """Message when no favorites exist."""
    return "Обране порожнє. Знайди щось класне і тисни ⭐!"


def error_message() -> str:
    """Generic error message."""
    return "Ой, щось пішло не так. Спробуй ще раз або тисни /start."


def flow_expired() -> str:
    """Message when flow state expired."""
    return "Давай почнемо спочатку — тисни кнопку нижче."


def miss_reason_prompt() -> str:
    """Prompt for miss reason selection."""
    return "Що саме не підійшло?"


def miss_recovery() -> str:
    """Message before showing recovery recommendation."""
    return "Зрозумів, шукаю щось краще..."


# Legacy constants for backwards compatibility
WELCOME_MESSAGE = start_message()
HELP_MESSAGE = (
    "<b>Доступні команди:</b>\n\n"
    "/start - Отримати нову рекомендацію\n"
    "/history - Переглянути історію\n"
    "/favorites - Переглянути обране\n"
    "/reset - Скинути вподобання\n"
    "/credits - Інформація про джерела\n"
    "/help - Показати цю довідку"
)

CREDITS_MESSAGE = (
    "Цей продукт використовує TMDB API, але не є схваленим або сертифікованим TMDB."
)
ERROR_MESSAGE = error_message()
RATE_LIMIT_MESSAGE = "Забагато запитів. Зачекай трохи і спробуй знову."
