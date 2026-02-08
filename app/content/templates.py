"""Post templates for channel content generation.

Defines 5 post formats with LLM prompts and fallback templates.
"""

from dataclasses import dataclass
from typing import Any

from app.config import config


@dataclass
class PostFormat:
    """Definition of a post format."""

    format_id: str
    name: str
    intent: str
    required_items: int
    system_prompt: str
    user_prompt_template: str
    fallback_template: str


# Format A: One Pick Emotion
ONE_PICK_EMOTION = PostFormat(
    format_id="one_pick_emotion",
    name="One Pick Emotion",
    intent="Emotional hook leading to a single recommendation",
    required_items=1,
    system_prompt="""Ти — копірайтер для українського Telegram-каналу про кіно.
Пиши коротко, емоційно, людською мовою.

СУВОРІ ПРАВИЛА:
- Перший рядок (хук) — максимум {hook_max} символів
- Весь текст — максимум {body_max} символів
- Максимум 6 рядків
- НЕ використовуй слова: топ, IMDb, рейтинг, найкращий, must-watch, шедевр
- НЕ розкривай сюжет, твісти, кінцівку
- Пиши українською
- Тон: дружній, неформальний, без пафосу""",
    user_prompt_template="""Напиши пост про фільм/серіал.

Назва: {title}
Тип: {item_type}
Теги настрою: {mood_tags}
Теги темпу: {pace_tags}

Формат:
1. Емоційний хук (питання або твердження про настрій/ситуацію)
2. Коротко про фільм (1-2 речення, без спойлерів)
3. Для кого підійде

{cta_instruction}""",
    fallback_template="""Коли хочеться {mood_phrase}...

«{title}» — саме те.
{type_phrase}, {pace_phrase}.

{cta_line}""",
)

# Format B: If Liked X Then Y
IF_LIKED_X_THEN_Y = PostFormat(
    format_id="if_liked_x_then_y",
    name="If Liked X Then Y",
    intent="Recommendation based on similarity to known title",
    required_items=2,
    system_prompt="""Ти — копірайтер для українського Telegram-каналу про кіно.
Пиши коротко, емоційно, людською мовою.

СУВОРІ ПРАВИЛА:
- Перший рядок (хук) — максимум {hook_max} символів
- Весь текст — максимум {body_max} символів
- Максимум 6 рядків
- НЕ використовуй слова: топ, IMDb, рейтинг, найкращий, must-watch, шедевр
- НЕ розкривай сюжет, твісти, кінцівку
- Пиши українською""",
    user_prompt_template="""Напиши пост у форматі "якщо сподобався X, спробуй Y".

Відомий фільм (X): {title_x}
Рекомендація (Y): {title_y}
Тип Y: {item_type_y}
Спільне: {common_tags}

Формат:
1. Хук з назвою X
2. Чому Y схожий (1 речення)
3. Чим Y особливий

{cta_instruction}""",
    fallback_template="""Якщо зайшов «{title_x}»...

Спробуй «{title_y}».
{similarity_phrase}.

{cta_line}""",
)

# Format C: Fact Then Pick
FACT_THEN_PICK = PostFormat(
    format_id="fact_then_pick",
    name="Fact Then Pick",
    intent="Interesting fact leading to recommendation",
    required_items=1,
    system_prompt="""Ти — копірайтер для українського Telegram-каналу про кіно.
Пиши коротко, емоційно, людською мовою.

СУВОРІ ПРАВИЛА:
- Перший рядок (хук) — максимум {hook_max} символів
- Весь текст — максимум {body_max} символів
- Максимум 6 рядків
- НЕ використовуй слова: топ, IMDb, рейтинг, найкращий, must-watch, шедевр
- НЕ розкривай сюжет, твісти, кінцівку
- Факт має бути цікавим, але НЕ спойлером
- Пиши українською""",
    user_prompt_template="""Напиши пост з цікавим фактом про фільм/серіал.

Назва: {title}
Тип: {item_type}
Опис: {overview}
Теги: {tags}

Формат:
1. Цікавий факт (хук)
2. Як це пов'язано з фільмом
3. Чому варто подивитись

{cta_instruction}""",
    fallback_template="""Цікавий факт 🎬

«{title}» — {fact_phrase}.
{type_phrase}, що варто побачити.

{cta_line}""",
)

# Format D: Poll
POLL = PostFormat(
    format_id="poll",
    name="Poll",
    intent="Engagement poll about movie preferences",
    required_items=0,
    system_prompt="""Ти — копірайтер для українського Telegram-каналу про кіно.
Пиши коротко, емоційно, людською мовою.

СУВОРІ ПРАВИЛА:
- Перший рядок (хук) — максимум {hook_max} символів
- Весь текст — максимум {body_max} символів
- Максимум 6 рядків
- Використовуй емодзі для варіантів (🔥, 💙, 🎬, ⚡)
- Пиши українською
- Це НЕ Telegram poll, а текстовий пост з реакціями""",
    user_prompt_template="""Напиши пост-опитування для каналу про кіно.

Тема: {poll_topic}
Варіанти: {options}

Формат:
1. Питання (хук)
2. 2-4 варіанти з емодзі
3. Заклик голосувати реакціями

{cta_instruction}""",
    fallback_template="""{poll_question}

🔥 {option_1}
💙 {option_2}
{extra_options}

Голосуй реакцією!

{cta_line}""",
)

# Format E: Bot Teaser
BOT_TEASER = PostFormat(
    format_id="bot_teaser",
    name="Bot Teaser",
    intent="Promote the recommendation bot",
    required_items=0,
    system_prompt="""Ти — копірайтер для українського Telegram-каналу про кіно.
Пиши коротко, емоційно, людською мовою.

СУВОРІ ПРАВИЛА:
- Перший рядок (хук) — максимум {hook_max} символів
- Весь текст — максимум {body_max} символів
- Максимум 6 рядків
- НЕ використовуй слова: топ, найкращий, must-watch
- Фокус на користі бота: швидкий підбір за настроєм
- Пиши українською""",
    user_prompt_template="""Напиши пост-тизер для бота підбору фільмів.

Бот: @{bot_username}
Що робить: підбирає фільм/серіал за 3 питання про настрій

Формат:
1. Хук про проблему (не знаєш що дивитись)
2. Рішення (бот)
3. Як працює (3 питання → рекомендація)

В кінці ОБОВ'ЯЗКОВО додай саме цей рядок без змін:
{bot_cta_line}""",
    fallback_template="""Не знаєш що дивитись? 🎬

Бот підбере фільм за твій настрій.
3 питання — 1 рекомендація.

{bot_cta_line}""",
)

# Registry of all formats
FORMATS: dict[str, PostFormat] = {
    "one_pick_emotion": ONE_PICK_EMOTION,
    "if_liked_x_then_y": IF_LIKED_X_THEN_Y,
    "fact_then_pick": FACT_THEN_PICK,
    "poll": POLL,
    "bot_teaser": BOT_TEASER,
}


def get_format(format_id: str) -> PostFormat | None:
    """Get format by ID."""
    return FORMATS.get(format_id)


def get_all_formats() -> list[PostFormat]:
    """Get all available formats."""
    return list(FORMATS.values())


def render_fallback(
    format_id: str,
    items: list[dict[str, Any]],
    cta_line: str,
    **kwargs: Any,
) -> str:
    """Render fallback template for a format.

    Args:
        format_id: Format identifier
        items: List of item dicts with title, type, tags, etc.
        cta_line: CTA line to append (or empty string)
        **kwargs: Additional template variables

    Returns:
        Rendered post text
    """
    fmt = get_format(format_id)
    if not fmt:
        return ""

    # Prepare common substitutions
    subs: dict[str, str] = {"cta_line": cta_line, **kwargs}

    if format_id == "one_pick_emotion" and items:
        item = items[0]
        subs["title"] = item.get("title", "")
        subs["mood_phrase"] = _mood_to_phrase(item.get("mood", []))
        subs["type_phrase"] = "Фільм" if item.get("type") == "movie" else "Серіал"
        subs["pace_phrase"] = _pace_to_phrase(item.get("pace", []))

    elif format_id == "if_liked_x_then_y" and len(items) >= 2:
        subs["title_x"] = items[0].get("title", "")
        subs["title_y"] = items[1].get("title", "")
        subs["similarity_phrase"] = _similarity_phrase(items[0], items[1])

    elif format_id == "fact_then_pick" and items:
        item = items[0]
        subs["title"] = item.get("title", "")
        subs["fact_phrase"] = _generic_fact_phrase(item)
        subs["type_phrase"] = "Фільм" if item.get("type") == "movie" else "Серіал"

    elif format_id == "poll":
        subs["poll_question"] = kwargs.get("poll_question", "Який настрій сьогодні?")
        subs["option_1"] = kwargs.get("option_1", "Щось легке")
        subs["option_2"] = kwargs.get("option_2", "Щось глибоке")
        subs["extra_options"] = kwargs.get("extra_options", "")

    elif format_id == "bot_teaser":
        pass  # cta_line already included

    template = fmt.fallback_template
    for key, value in subs.items():
        template = template.replace("{" + key + "}", value)

    return template.strip()


def _mood_to_phrase(mood: list[str]) -> str:
    """Convert mood tags to Ukrainian phrase."""
    mood_map = {
        "light": "чогось легкого",
        "heavy": "чогось глибокого",
        "escape": "втекти від реальності",
    }
    if mood:
        return mood_map.get(mood[0], "гарного кіно")
    return "гарного кіно"


def _pace_to_phrase(pace: list[str]) -> str:
    """Convert pace tags to Ukrainian phrase."""
    pace_map = {
        "slow": "неспішний і вдумливий",
        "fast": "динамічний і захопливий",
    }
    if pace:
        return pace_map.get(pace[0], "")
    return ""


def _similarity_phrase(item_x: dict, item_y: dict) -> str:
    """Generate similarity phrase between two items."""
    # Find common tags
    mood_x = set(item_x.get("mood", []))
    mood_y = set(item_y.get("mood", []))
    common_mood = mood_x & mood_y

    if "escape" in common_mood:
        return "Так само затягує"
    if "heavy" in common_mood:
        return "Така ж глибина"
    if "light" in common_mood:
        return "Так само легко"

    return "Схожа атмосфера"


def _generic_fact_phrase(item: dict) -> str:
    """Generate a generic fact phrase for an item."""
    item_type = item.get("type", "movie")
    tone = item.get("tone", [])

    if "dark" in tone:
        return "історія з темною атмосферою"
    if "funny" in tone:
        return "історія що змусить посміхнутись"
    if "warm" in tone:
        return "тепла історія"

    if item_type == "series":
        return "серіал що затягує"
    return "історія що запам'ятовується"
