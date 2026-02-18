"""Rationale and when-to-watch generation for recommendations (Ukrainian)."""

import hashlib
import re
from typing import Any

# Maximum rationale length
MAX_RATIONALE_LENGTH = 320

# Spoiler keywords to avoid (both EN and UA)
SPOILER_KEYWORDS = frozenset([
    "twist",
    "ending",
    "killer",
    "dies",
    "murderer",
    "plot twist",
    "finale",
    "death",
    "killed",
    "betrayal",
    "reveal",
    "shocking",
    "surprise ending",
    "поворот",
    "кінцівка",
    "вбивця",
    "помирає",
    "гине",
    "зрада",
    "фінал",
])

# Rationale templates indexed by state (Ukrainian)
RATIONALE_TEMPLATES: dict[str, list[str]] = {
    "light": [
        "Легке кіно, яке не навантажує. Саме те, щоб розслабитись після довгого дня.",
        "Простий і приємний перегляд. Сідай зручніше і насолоджуйся.",
        "Щось світле, щоб підняти настрій. Ніякого напруження.",
        "Тепла, невимушена історія — те, що зараз потрібно.",
        "Комфортний перегляд. Дозволь собі щось просте і приємне.",
    ],
    "heavy": [
        "Глибока історія, яка залишається з тобою надовго.",
        "Серйозне кіно для тих, хто готовий відчути щось справжнє.",
        "Потужний наратив, що винагороджує увагу.",
        "Багатошарова розповідь, що запрошує до роздумів.",
        "Вагоме кіно, яке залишає слід. Варте твоєї повної уваги.",
    ],
    "escape": [
        "Чистий ескейпізм. Дозволь собі повністю загубитись в іншому світі.",
        "Подорож далеко від буденності, як ти й просив. Занурюйся.",
        "Захоплива історія, що переносить кудись зовсім інакше.",
        "Повне занурення в іншу реальність. Забудь про все на якийсь час.",
        "Пригода чекає. Крокни крізь екран і залиш свій світ позаду.",
    ],
}

# Pace-based modifiers (appended to rationale)
PACE_MODIFIERS: dict[str, list[str]] = {
    "slow": [
        "Кіно не поспішає, і це добре.",
        "Неквапливий темп, що дає моментам дихати.",
        "Споглядальний ритм для вдумливого перегляду.",
    ],
    "fast": [
        "Жвавий темп, що тримає в напрузі.",
        "Динаміка, яка не відпускає.",
        "Енергійно від початку до кінця.",
    ],
}

# When-to-watch templates based on state + pace (Ukrainian)
WHEN_TO_WATCH: dict[str, dict[str, list[str]]] = {
    "light": {
        "slow": [
            "Найкраще без відволікань, з теплим напоєм.",
            "Ідеально для тихого вечора, коли хочеш розслабитись.",
            "Для спокійного завершення дня.",
        ],
        "fast": [
            "Коли хочеш легких розваг з енергією.",
            "Для вихідних, коли потрібен драйв без напруги.",
            "Коли хочеш чогось легкого, але жвавого.",
        ],
    },
    "heavy": {
        "slow": [
            "Виділи час без відволікань. Це кіно винагороджує терпіння.",
            "Для пізнього вечора, коли можеш повністю зосередитись.",
            "Коли готовий по-справжньому зануритись в історію.",
        ],
        "fast": [
            "Коли хочеш інтенсивності без затягування.",
            "Захоплюючий перегляд, що вимагає уваги.",
            "Коли хочеш чогось серйозного, але динамічного.",
        ],
    },
    "escape": {
        "slow": [
            "Влаштуйся зручно для подорожі. Дай світу побудуватись навколо.",
            "Для лінивого дня, коли хочеш зникнути кудись.",
            "Коли є час повністю зануритись.",
        ],
        "fast": [
            "Пристебнись — це атракціон, що не відпускає.",
            "Коли хочеш пригод з місця в кар'єр.",
            "Для захопливої втечі від реальності.",
        ],
    },
}

# Another-but-different delta explainers (Ukrainian)
DELTA_EXPLAINERS: dict[str, list[str]] = {
    "pace_flipped": [
        "Тепер {new_pace}, але той самий настрій.",
        "Ось щось {new_pace}.",
        "Та сама атмосфера, інший ритм — {new_pace}.",
    ],
    "tone_shifted": [
        "Схоже відчуття, інший відтінок.",
        "Залишаюсь у настрої, змінюю акцент.",
        "Та сама суть, новий підхід.",
    ],
    "format_flipped": [
        "Цього разу {new_format}.",
        "Той самий вайб, тепер як {new_format}.",
        "Змінюю формат на {new_format}.",
    ],
}

# Ukrainian pace words for delta explainer
PACE_WORDS_UA = {
    "slow": "повільніше",
    "fast": "динамічніше",
}

FORMAT_WORDS_UA = {
    "movie": "фільм",
    "series": "серіал",
}


def _hash_seed(rec_id: str, salt: str = "") -> int:
    """Generate deterministic hash from rec_id.

    Args:
        rec_id: Recommendation ID
        salt: Optional salt for variation

    Returns:
        Integer hash value
    """
    combined = f"{rec_id}{salt}"
    hash_bytes = hashlib.sha256(combined.encode()).digest()
    return int.from_bytes(hash_bytes[:4], "big")


def _select_by_hash(options: list[str], rec_id: str, salt: str = "") -> str:
    """Select option deterministically by hash.

    Args:
        options: List of options
        rec_id: Recommendation ID for hashing
        salt: Optional salt

    Returns:
        Selected option
    """
    if not options:
        return ""
    idx = _hash_seed(rec_id, salt) % len(options)
    return options[idx]


def _contains_spoiler(text: str) -> bool:
    """Check if text contains spoiler keywords.

    Args:
        text: Text to check

    Returns:
        True if contains spoiler
    """
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in SPOILER_KEYWORDS)


def _sanitize_text(text: str, max_length: int = MAX_RATIONALE_LENGTH) -> str:
    """Sanitize and truncate text.

    Args:
        text: Text to sanitize
        max_length: Maximum length

    Returns:
        Sanitized text
    """
    # Remove any spoiler keywords by replacing them
    result = text
    for keyword in SPOILER_KEYWORDS:
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        result = pattern.sub("...", result)

    # Truncate if needed
    if len(result) > max_length:
        result = result[: max_length - 3] + "..."

    return result


def generate_rationale(
    rec_id: str,
    answers: dict[str, str],
    item_tags: dict[str, Any] | None = None,
) -> str:
    """Generate recommendation rationale.

    Args:
        rec_id: Recommendation ID (for deterministic selection)
        answers: User answers
        item_tags: Optional item tags for customization

    Returns:
        Rationale string (<= 320 chars, no spoilers)
    """
    state = answers.get("state", "escape")
    pace = answers.get("pace", "slow")

    # Get base rationale for state
    templates = RATIONALE_TEMPLATES.get(state, RATIONALE_TEMPLATES["escape"])
    base = _select_by_hash(templates, rec_id, "rationale")

    # Optionally add pace modifier (50% chance based on hash)
    if _hash_seed(rec_id, "pace_mod") % 2 == 0:
        modifiers = PACE_MODIFIERS.get(pace, PACE_MODIFIERS["slow"])
        modifier = _select_by_hash(modifiers, rec_id, "pace")
        base = f"{base} {modifier}"

    return _sanitize_text(base)


def generate_when_to_watch(
    rec_id: str,
    answers: dict[str, str],
) -> str:
    """Generate when-to-watch suggestion.

    Args:
        rec_id: Recommendation ID
        answers: User answers

    Returns:
        When-to-watch string
    """
    state = answers.get("state", "escape")
    pace = answers.get("pace", "slow")

    state_templates = WHEN_TO_WATCH.get(state, WHEN_TO_WATCH["escape"])
    pace_templates = state_templates.get(pace, state_templates.get("slow", []))

    if not pace_templates:
        return "Коли будеш готовий до чогось класного."

    return _select_by_hash(pace_templates, rec_id, "when")


def generate_delta_explainer(
    delta_type: str,
    new_value: str,
    rec_id: str,
) -> str:
    """Generate explanation for 'another-but-different' delta.

    Args:
        delta_type: Type of change (pace_flipped, tone_shifted, format_flipped)
        new_value: The new value (e.g., "fast", "movie")
        rec_id: Recommendation ID

    Returns:
        Delta explanation string
    """
    templates = DELTA_EXPLAINERS.get(delta_type, DELTA_EXPLAINERS["tone_shifted"])
    template = _select_by_hash(templates, rec_id, "delta")

    # Replace placeholders with Ukrainian words
    if delta_type == "pace_flipped":
        ua_pace = PACE_WORDS_UA.get(new_value, new_value)
        return template.replace("{new_pace}", ua_pace)
    elif delta_type == "format_flipped":
        ua_format = FORMAT_WORDS_UA.get(new_value, new_value)
        return template.replace("{new_format}", ua_format)

    return template


async def generate_hint_rationale(
    hint_text: str,
    item_title: str,
    overview: str | None,
) -> str | None:
    """Generate one-sentence LLM explanation why item matches the hint.

    Returns None on any error (caller falls back to template-only).
    """
    if not hint_text or not overview:
        return None

    try:
        from app.llm.llm_adapter import LLMDisabledError, OpenAIError, generate_text

        response = await generate_text(
            system_prompt=(
                "You are a movie/series recommendation assistant. "
                "In ONE short sentence in Ukrainian (max 120 chars), explain why the film/series "
                "matches the user's request. Be specific and concrete. No spoilers."
            ),
            user_prompt=(
                f"User request: {hint_text}\n"
                f"Film/series: {item_title}\n"
                f"Description: {overview[:600]}"
            ),
            max_tokens=80,
            temperature=0.3,
        )
        text = response.strip()
        if _contains_spoiler(text):
            return None
        return _sanitize_text(text, max_length=150)

    except (LLMDisabledError, OpenAIError):
        return None
    except Exception:
        return None


def validate_rationale(rationale: str) -> tuple[bool, str | None]:
    """Validate rationale meets requirements.

    Args:
        rationale: Rationale text to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(rationale) > MAX_RATIONALE_LENGTH:
        return False, f"Rationale too long: {len(rationale)} > {MAX_RATIONALE_LENGTH}"

    if _contains_spoiler(rationale):
        return False, "Rationale contains spoiler keywords"

    return True, None
