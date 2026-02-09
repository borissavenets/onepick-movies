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

# Format F: Mood Trio
MOOD_TRIO = PostFormat(
    format_id="mood_trio",
    name="Mood Trio",
    intent="Three picks for one mood — compact list",
    required_items=3,
    system_prompt="""Ти — копірайтер для українського Telegram-каналу про кіно.
Пиши коротко, емоційно, людською мовою.

СУВОРІ ПРАВИЛА:
- Перший рядок (хук) — максимум {hook_max} символів
- Весь текст — максимум {body_max} символів
- Максимум 6 рядків
- НЕ використовуй слова: топ, IMDb, рейтинг, найкращий, must-watch, шедевр
- НЕ розкривай сюжет, твісти, кінцівку
- Пиши українською
- Формат: нумерований список із 3 назв з міні-описом (3-5 слів кожен)""",
    user_prompt_template="""Напиши пост-добірку «3 фільми/серіали під настрій».

Настрій: {mood_label}
1. {title_1} ({type_1}) — теги: {tags_1}
2. {title_2} ({type_2}) — теги: {tags_2}
3. {title_3} ({type_3}) — теги: {tags_3}

Формат:
1. Хук про настрій (питання або ситуація)
2. Три пункти: емодзі + назва + 3-5 слів чому
3. Заклик зберегти / поділитись

{cta_instruction}""",
    fallback_template="""Настрій: {mood_label} 🎬

1. «{title_1}» — {micro_1}
2. «{title_2}» — {micro_2}
3. «{title_3}» — {micro_3}

{cta_line}""",
)

# Format G: Versus
VERSUS = PostFormat(
    format_id="versus",
    name="Versus",
    intent="X vs Y comparison — audience votes with reactions",
    required_items=2,
    system_prompt="""Ти — копірайтер для українського Telegram-каналу про кіно.
Пиши коротко, емоційно, людською мовою.

СУВОРІ ПРАВИЛА:
- Перший рядок (хук) — максимум {hook_max} символів
- Весь текст — максимум {body_max} символів
- Максимум 6 рядків
- НЕ використовуй слова: топ, IMDb, рейтинг, найкращий, must-watch, шедевр
- НЕ розкривай сюжет, твісти, кінцівку
- Пиши українською
- В кінці запропонуй голосувати реакціями (🔥 та 💙)""",
    user_prompt_template="""Напиши пост-батл «X проти Y».

X: {title_x} ({type_x}) — теги: {tags_x}
Y: {title_y} ({type_y}) — теги: {tags_y}
Спільне: {common}

Формат:
1. Хук-питання (що обереш?)
2. 🔥 X — 1 речення чому крутий
3. 💙 Y — 1 речення чому крутий
4. Голосуй реакцією!

{cta_instruction}""",
    fallback_template="""Що обереш? 🤔

🔥 «{title_x}» — {micro_x}
💙 «{title_y}» — {micro_y}

Голосуй реакцією!

{cta_line}""",
)

# Format H: Quote Hook
QUOTE_HOOK = PostFormat(
    format_id="quote_hook",
    name="Quote Hook",
    intent="Atmospheric situational hook leading to a pick",
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
- Хук: опиши атмосферу / ситуацію / відчуття (як цитата з фільму, але не пряма цитата)""",
    user_prompt_template="""Напиши пост з атмосферним хуком.

Назва: {title}
Тип: {item_type}
Опис: {overview}
Теги настрою: {mood_tags}
Теги тону: {tone_tags}

Формат:
1. Атмосферний хук — опиши ситуацію чи відчуття (ніби цитата з життя), курсивом
2. Рекомендація: назва + 1 речення
3. Для кого підійде

{cta_instruction}""",
    fallback_template="""<i>{atmosphere_phrase}</i>

«{title}» — {type_phrase}, {tone_phrase}.

{cta_line}""",
)

# Registry of all formats
FORMATS: dict[str, PostFormat] = {
    "one_pick_emotion": ONE_PICK_EMOTION,
    "if_liked_x_then_y": IF_LIKED_X_THEN_Y,
    "fact_then_pick": FACT_THEN_PICK,
    "poll": POLL,
    "bot_teaser": BOT_TEASER,
    "mood_trio": MOOD_TRIO,
    "versus": VERSUS,
    "quote_hook": QUOTE_HOOK,
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

    elif format_id == "mood_trio" and len(items) >= 3:
        subs["mood_label"] = _mood_to_label(items[0].get("mood", []))
        for i, item in enumerate(items[:3], 1):
            subs[f"title_{i}"] = item.get("title", "")
            subs[f"micro_{i}"] = _micro_description(item)

    elif format_id == "versus" and len(items) >= 2:
        subs["title_x"] = items[0].get("title", "")
        subs["title_y"] = items[1].get("title", "")
        subs["micro_x"] = _micro_description(items[0])
        subs["micro_y"] = _micro_description(items[1])

    elif format_id == "quote_hook" and items:
        item = items[0]
        subs["title"] = item.get("title", "")
        subs["atmosphere_phrase"] = _atmosphere_phrase(item)
        subs["type_phrase"] = "фільм" if item.get("type") == "movie" else "серіал"
        subs["tone_phrase"] = _tone_to_phrase(item.get("tone", []))

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


def _mood_to_label(mood: list[str]) -> str:
    """Convert mood tags to a short Ukrainian label."""
    mood_map = {
        "light": "щось легке",
        "heavy": "щось глибоке",
        "escape": "втекти від реальності",
    }
    if mood:
        return mood_map.get(mood[0], "гарне кіно")
    return "гарне кіно"


def _micro_description(item: dict) -> str:
    """Generate a 3-5 word micro-description for list formats."""
    tone = item.get("tone", [])
    pace = item.get("pace", [])
    item_type = item.get("type", "movie")

    if "dark" in tone and "slow" in pace:
        return "повільна темна атмосфера"
    if "dark" in tone:
        return "темна й напружена"
    if "funny" in tone and "fast" in pace:
        return "швидка й смішна"
    if "funny" in tone:
        return "легкий гумор"
    if "warm" in tone and "slow" in pace:
        return "тепла й неспішна"
    if "warm" in tone:
        return "тепла історія"
    if "fast" in pace:
        return "динамічна й захоплива"
    if "slow" in pace:
        return "неспішна й вдумлива"
    if item_type == "series":
        return "серіал що затягує"
    return "варто побачити"


def _tone_to_phrase(tone: list[str]) -> str:
    """Convert tone tags to Ukrainian phrase."""
    tone_map = {
        "dark": "з темною атмосферою",
        "funny": "з гумором",
        "warm": "теплий і щирий",
        "tense": "напружений",
        "romantic": "романтичний",
    }
    if tone:
        return tone_map.get(tone[0], "атмосферний")
    return "атмосферний"


def _atmosphere_phrase(item: dict) -> str:
    """Generate an atmospheric hook phrase for quote_hook format."""
    mood = item.get("mood", [])
    tone = item.get("tone", [])

    if "escape" in mood and "dark" in tone:
        return "Коли хочеться зникнути в іншому світі, де все складно, але чесно..."
    if "escape" in mood:
        return "Коли реальність набридла і хочеться просто провалитись у екран..."
    if "heavy" in mood and "dark" in tone:
        return "Вечір, тиша, і бажання відчути щось по-справжньому..."
    if "heavy" in mood:
        return "Іноді хочеться кіно, після якого довго мовчиш..."
    if "light" in mood and "funny" in tone:
        return "Коли треба просто вимкнути голову і посміятись..."
    if "light" in mood and "warm" in tone:
        return "Коли хочеться чогось теплого, як какао у дощовий день..."
    if "light" in mood:
        return "Легкий настрій, вільний вечір — саме час..."

    return "Буває такий настрій, коли потрібен саме правильний фільм..."
