"""Channel post generator pipeline.

Wires together: selector -> templates -> LLM -> style_lint -> output.
Supports fallback to deterministic templates when LLM is disabled or fails.
"""

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.content.selector import (
    SelectedItem,
    select_for_fact,
    select_for_if_liked,
    select_for_one_pick,
    select_items_for_format,
)
from app.content.style_lint import fix_common_issues, lint_post, truncate_to_limits
from app.content.templates import FORMATS, render_fallback
from app.logging import get_logger

logger = get_logger(__name__)

MAX_LLM_RETRIES = 2

# Static posters for formats without film items
_STATIC_POSTERS_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "posters"
STATIC_POSTERS: dict[str, Path] = {
    "poll": _STATIC_POSTERS_DIR / "poll.png",
    "bot_teaser": _STATIC_POSTERS_DIR / "bot_teaser.png",
}

# Poll topics and options for deterministic fallback
POLL_TOPICS = [
    {
        "question": "Який настрій сьогодні?",
        "options": ["Щось легке", "Щось глибоке", "Втекти від реальності"],
    },
    {
        "question": "Що обираєш на вечір?",
        "options": ["Фільм", "Серіал", "Ще не вирішив"],
    },
    {
        "question": "Ідеальне кіно для дощового дня?",
        "options": ["Затишна драма", "Динамічний трилер", "Легка комедія"],
    },
    {
        "question": "Як дивишся кіно?",
        "options": ["Один/одна", "З кимось", "Залежить від настрою"],
    },
]


@dataclass
class GeneratedPost:
    """Result of post generation."""

    text: str
    meta_json: str
    format_id: str
    lint_passed: bool
    used_llm: bool
    poster_url: str | None = None


def _build_bot_deeplink(post_id: str, variant_id: str) -> str:
    """Build a bot deep-link URL for CTA."""
    return f"https://t.me/{config.bot_username}?start=post_{post_id}_v{variant_id}"


def _should_include_cta(hypothesis_id: str) -> bool:
    """Decide whether to include CTA based on CTA_RATE.

    Seeded per day + hypothesis for stability.
    """
    today = hashlib.md5(
        f"{hypothesis_id}:{__import__('datetime').date.today().isoformat()}".encode()
    ).hexdigest()
    return int(today[:8], 16) / 0xFFFFFFFF <= config.cta_rate


def _build_cta_line(bot_deeplink: str) -> str:
    """Build the CTA line for posts with a pretty HTML link."""
    return f'🎬 <a href="{bot_deeplink}">Підібрати фільм за настроєм</a>'


def _item_to_dict(item: SelectedItem) -> dict[str, Any]:
    """Convert SelectedItem to dict for template rendering."""
    return {
        "item_id": item.item_id,
        "title": item.title,
        "type": item.item_type,
        "mood": item.tags.get("mood", []),
        "pace": item.tags.get("pace", []),
        "tone": item.tags.get("tone", []),
        "overview": item.overview or "",
        "rating": item.rating,
    }


async def _try_llm_generate(
    format_id: str,
    items: list[SelectedItem],
    cta_line: str,
    bot_deeplink: str,
) -> str | None:
    """Try generating text via LLM with retry on lint failure.

    Returns generated text or None if LLM is unavailable/fails.
    """
    try:
        from app.llm.openai_adapter import LLMDisabledError, generate_text
    except ImportError:
        logger.warning("OpenAI adapter not available")
        return None

    fmt = FORMATS.get(format_id)
    if not fmt:
        return None

    # Build system prompt with limits
    system_prompt = fmt.system_prompt.format(
        hook_max=config.post_hook_max_chars,
        body_max=config.post_body_max_chars,
    )

    # Build user prompt based on format
    cta_instruction = (
        f'Додай в кінці рядок: "{cta_line}"' if cta_line else "Без CTA."
    )

    user_prompt = _build_user_prompt(format_id, items, cta_instruction, bot_deeplink)
    if not user_prompt:
        return None

    for attempt in range(MAX_LLM_RETRIES + 1):
        try:
            if attempt > 0:
                system_prompt += (
                    f"\n\nПОПЕРЕДНЯ СПРОБА НЕ ПРОЙШЛА ПЕРЕВІРКУ СТИЛЮ. "
                    f"Будь лаконічнішим: хук до {config.post_hook_max_chars} символів, "
                    f"весь текст до {config.post_body_max_chars} символів, максимум 6 рядків."
                )

            text = await generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=400,
                temperature=0.8,
            )

            if not text:
                continue

            # Fix common issues automatically
            text = fix_common_issues(text)
            text = truncate_to_limits(text)

            # Lint check
            result = lint_post(text)
            if result.passed:
                logger.info(f"LLM generated post for {format_id} (attempt {attempt + 1})")
                return text

            logger.warning(
                f"LLM output failed lint (attempt {attempt + 1}): "
                f"{[v.rule for v in result.violations]}"
            )

        except LLMDisabledError:
            logger.debug("LLM disabled, using fallback")
            return None

        except Exception as e:
            logger.warning(f"LLM generation error (attempt {attempt + 1}): {e}")
            if attempt == MAX_LLM_RETRIES:
                return None

    return None


def _build_user_prompt(
    format_id: str,
    items: list[SelectedItem],
    cta_instruction: str,
    bot_deeplink: str,
) -> str | None:
    """Build user prompt for LLM based on format."""
    fmt = FORMATS.get(format_id)
    if not fmt:
        return None

    if format_id == "one_pick_emotion" and items:
        item = items[0]
        return fmt.user_prompt_template.format(
            title=item.title,
            item_type="фільм" if item.item_type == "movie" else "серіал",
            mood_tags=", ".join(item.tags.get("mood", [])) or "невідомо",
            pace_tags=", ".join(item.tags.get("pace", [])) or "невідомо",
            cta_instruction=cta_instruction,
        )

    elif format_id == "if_liked_x_then_y" and len(items) >= 2:
        common_tags = set(items[0].tags.get("mood", [])) & set(
            items[1].tags.get("mood", [])
        )
        return fmt.user_prompt_template.format(
            title_x=items[0].title,
            title_y=items[1].title,
            item_type_y="фільм" if items[1].item_type == "movie" else "серіал",
            common_tags=", ".join(common_tags) if common_tags else "атмосфера",
            cta_instruction=cta_instruction,
        )

    elif format_id == "fact_then_pick" and items:
        item = items[0]
        all_tags = []
        for key in ("mood", "pace", "tone"):
            all_tags.extend(item.tags.get(key, []))
        return fmt.user_prompt_template.format(
            title=item.title,
            item_type="фільм" if item.item_type == "movie" else "серіал",
            overview=item.overview or "Інформація відсутня",
            tags=", ".join(all_tags) if all_tags else "невідомо",
            cta_instruction=cta_instruction,
        )

    elif format_id == "poll":
        topic = random.choice(POLL_TOPICS)
        return fmt.user_prompt_template.format(
            poll_topic=topic["question"],
            options=", ".join(topic["options"]),
            cta_instruction=cta_instruction,
        )

    elif format_id == "bot_teaser":
        bot_cta = f'🎬 <a href="{bot_deeplink}">Спробуй @{config.bot_username}</a>'
        return fmt.user_prompt_template.format(
            bot_username=config.bot_username,
            bot_cta_line=bot_cta,
        )

    return None


def _generate_fallback(
    format_id: str,
    items: list[SelectedItem],
    cta_line: str,
    bot_deeplink_url: str | None = None,
) -> str:
    """Generate post using deterministic fallback templates."""
    item_dicts = [_item_to_dict(item) for item in items]

    if format_id == "poll":
        topic = random.choice(POLL_TOPICS)
        extra = ""
        if len(topic["options"]) > 2:
            extra = f"\U0001f3ac {topic['options'][2]}"
        return render_fallback(
            format_id,
            item_dicts,
            cta_line,
            poll_question=topic["question"],
            option_1=topic["options"][0],
            option_2=topic["options"][1],
            extra_options=extra,
        )

    if format_id == "bot_teaser" and bot_deeplink_url:
        bot_cta = f'🎬 <a href="{bot_deeplink_url}">Спробуй @{config.bot_username}</a>'
        return render_fallback(
            format_id,
            item_dicts,
            cta_line,
            bot_cta_line=bot_cta,
        )

    return render_fallback(format_id, item_dicts, cta_line)


async def generate_post(
    session: AsyncSession,
    format_id: str,
    hypothesis_id: str,
    variant_id: str,
    bot_deeplink_url: str | None = None,
) -> GeneratedPost:
    """Generate a channel post.

    Main entry point for the content generation pipeline.

    Args:
        session: Database session for item selection
        format_id: Post format ID (one of 5 formats)
        hypothesis_id: A/B hypothesis identifier
        variant_id: Variant identifier within hypothesis
        bot_deeplink_url: Override bot deep-link URL (auto-generated if None)

    Returns:
        GeneratedPost with text, metadata, and status
    """
    # Validate format
    if format_id not in FORMATS:
        logger.error(f"Unknown format_id: {format_id}")
        return GeneratedPost(
            text="",
            meta_json=json.dumps({"error": f"Unknown format: {format_id}"}),
            format_id=format_id,
            lint_passed=False,
            used_llm=False,
        )

    fmt = FORMATS[format_id]

    # Build deep-link and CTA
    post_stub_id = hashlib.md5(
        f"{hypothesis_id}:{variant_id}".encode()
    ).hexdigest()[:8]

    if bot_deeplink_url is None:
        bot_deeplink_url = _build_bot_deeplink(post_stub_id, variant_id)

    include_cta = _should_include_cta(hypothesis_id)
    cta_line = _build_cta_line(bot_deeplink_url) if include_cta else ""

    # Select items
    items: list[SelectedItem] = []
    if format_id == "one_pick_emotion":
        item = await select_for_one_pick(session)
        if item:
            items = [item]
    elif format_id == "if_liked_x_then_y":
        pair = await select_for_if_liked(session)
        if pair:
            items = list(pair)
    elif format_id == "fact_then_pick":
        item = await select_for_fact(session)
        if item:
            items = [item]
    elif format_id in ("poll", "bot_teaser"):
        pass  # No items needed for text

    # Check if we have enough items
    if fmt.required_items > 0 and len(items) < fmt.required_items:
        logger.warning(
            f"Not enough items for {format_id}: need {fmt.required_items}, got {len(items)}"
        )
        return GeneratedPost(
            text="",
            meta_json=json.dumps({"error": "Not enough items available"}),
            format_id=format_id,
            lint_passed=False,
            used_llm=False,
        )

    # Try LLM generation
    used_llm = False
    text = None

    if config.llm_enabled:
        text = await _try_llm_generate(format_id, items, cta_line, bot_deeplink_url)
        if text:
            used_llm = True

    # Fallback to template
    if not text:
        text = _generate_fallback(format_id, items, cta_line, bot_deeplink_url)
        text = fix_common_issues(text)
        text = truncate_to_limits(text)

    # Final lint
    lint_result = lint_post(text)

    # Build metadata
    meta = {
        "items": [item.item_id for item in items],
        "format_id": format_id,
        "hypothesis_id": hypothesis_id,
        "variant_id": variant_id,
        "cta": include_cta,
        "language": config.post_language,
        "lint_passed": lint_result.passed,
        "used_llm": used_llm,
    }

    if not lint_result.passed:
        meta["lint_violations"] = [v.rule for v in lint_result.violations]
        logger.warning(
            f"Final post for {format_id} has lint violations: "
            f"{[v.rule for v in lint_result.violations]}"
        )

    # Get poster: from items for film formats, static image for poll/bot_teaser
    poster_url: str | None = None
    if items:
        poster_url = items[0].poster_url
    elif format_id in STATIC_POSTERS:
        static_path = STATIC_POSTERS[format_id]
        if static_path.exists():
            poster_url = str(static_path)

    logger.info(
        f"Generated post: format={format_id}, llm={used_llm}, "
        f"lint_passed={lint_result.passed}, items={len(items)}, "
        f"poster={'yes' if poster_url else 'no'}"
    )

    return GeneratedPost(
        text=text,
        meta_json=json.dumps(meta, ensure_ascii=False),
        format_id=format_id,
        lint_passed=lint_result.passed,
        used_llm=used_llm,
        poster_url=poster_url,
    )
