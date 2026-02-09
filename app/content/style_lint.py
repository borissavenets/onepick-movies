"""Style lint for channel post content.

Enforces style constraints on generated posts.
"""

import re
from dataclasses import dataclass

from app.config import config
from app.logging import get_logger

logger = get_logger(__name__)

_PROOFREAD_SYSTEM = (
    "Ти — коректор української мови. "
    "Виправ лише граматичні, орфографічні та пунктуаційні помилки. "
    "НЕ змінюй стиль, тон, HTML-теги, емодзі, посилання та структуру тексту. "
    "Поверни виправлений текст без пояснень."
)


async def proofread(text: str) -> str:
    """Run text through LLM to fix Ukrainian grammar/spelling.

    Returns original text unchanged if LLM is unavailable.
    """
    if not text or not text.strip():
        return text

    try:
        from app.llm.openai_adapter import LLMDisabledError, generate_text

        result = await generate_text(
            system_prompt=_PROOFREAD_SYSTEM,
            user_prompt=text,
            max_tokens=len(text) + 200,
            temperature=0.2,
        )
        if result and result.strip():
            return result.strip()
        return text
    except Exception as e:
        logger.debug(f"Proofread skipped: {e}")
        return text


@dataclass
class LintViolation:
    """A style violation found in content."""

    rule: str
    message: str
    severity: str = "error"  # "error" or "warning"


@dataclass
class LintResult:
    """Result of linting content."""

    passed: bool
    violations: list[LintViolation]
    text: str

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


def lint_post(text: str) -> LintResult:
    """Lint a post for style violations.

    Checks:
    - First line hook length
    - Total body length
    - Banned words
    - Spoiler words
    - Maximum lines
    - Double blank lines

    Args:
        text: Post text to lint

    Returns:
        LintResult with violations
    """
    violations: list[LintViolation] = []

    # Normalize text
    text = text.strip()
    lines = text.split("\n")

    # Rule 1: First line hook length
    if lines:
        first_line = lines[0].strip()
        if len(first_line) > config.post_hook_max_chars:
            violations.append(
                LintViolation(
                    rule="hook_length",
                    message=f"First line ({len(first_line)} chars) exceeds max {config.post_hook_max_chars}",
                    severity="error",
                )
            )

    # Rule 2: Total body length
    if len(text) > config.post_body_max_chars:
        violations.append(
            LintViolation(
                rule="body_length",
                message=f"Total length ({len(text)} chars) exceeds max {config.post_body_max_chars}",
                severity="error",
            )
        )

    # Rule 3: Banned words (case-insensitive)
    text_lower = text.lower()
    for word in config.banned_words:
        if word.lower() in text_lower:
            violations.append(
                LintViolation(
                    rule="banned_word",
                    message=f"Contains banned word: '{word}'",
                    severity="error",
                )
            )

    # Rule 4: Spoiler words (case-insensitive)
    for word in config.spoiler_words:
        if word.lower() in text_lower:
            violations.append(
                LintViolation(
                    rule="spoiler_word",
                    message=f"Contains spoiler word: '{word}'",
                    severity="error",
                )
            )

    # Rule 5: Maximum 6 lines (non-empty)
    non_empty_lines = [l for l in lines if l.strip()]
    if len(non_empty_lines) > 6:
        violations.append(
            LintViolation(
                rule="max_lines",
                message=f"Too many lines ({len(non_empty_lines)}), max is 6",
                severity="error",
            )
        )

    # Rule 6: No double blank lines
    prev_empty = False
    for i, line in enumerate(lines):
        is_empty = not line.strip()
        if is_empty and prev_empty:
            violations.append(
                LintViolation(
                    rule="double_blank",
                    message=f"Double blank line at line {i + 1}",
                    severity="warning",
                )
            )
        prev_empty = is_empty

    passed = all(v.severity != "error" for v in violations)

    if violations:
        logger.debug(
            f"Lint found {len(violations)} issues: "
            f"{[v.rule for v in violations]}"
        )

    return LintResult(
        passed=passed,
        violations=violations,
        text=text,
    )


def _markdown_to_html(text: str) -> str:
    """Convert Markdown bold/italic to HTML tags for Telegram."""
    # **bold** -> <b>bold</b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # *italic* -> <i>italic</i>  (but not inside URLs or HTML tags)
    text = re.sub(r"(?<![<\w/])\*([^*\n]+?)\*(?![>\w])", r"<i>\1</i>", text)
    # [text](url) -> <a href="url">text</a>
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def fix_common_issues(text: str) -> str:
    """Attempt to fix common lint issues.

    Args:
        text: Post text

    Returns:
        Fixed text (best effort)
    """
    text = text.strip()

    # Convert Markdown formatting to HTML
    text = _markdown_to_html(text)

    lines = text.split("\n")

    # Fix double blank lines
    fixed_lines: list[str] = []
    prev_empty = False
    for line in lines:
        is_empty = not line.strip()
        if is_empty and prev_empty:
            continue  # Skip second blank line
        fixed_lines.append(line)
        prev_empty = is_empty

    # If too many lines, try to merge some
    non_empty_count = sum(1 for l in fixed_lines if l.strip())
    if non_empty_count > 6:
        # Try to merge short consecutive lines
        merged: list[str] = []
        i = 0
        while i < len(fixed_lines):
            line = fixed_lines[i]
            if line.strip() and i + 1 < len(fixed_lines):
                next_line = fixed_lines[i + 1].strip()
                # Merge if both are short and next isn't starting a new section
                if (
                    next_line
                    and len(line.strip()) < 40
                    and len(next_line) < 40
                    and not next_line.startswith(("🔥", "💙", "🎬", "⚡", "➡"))
                ):
                    merged.append(line.strip() + " " + next_line)
                    i += 2
                    continue
            merged.append(line)
            i += 1
        fixed_lines = merged

    return "\n".join(fixed_lines)


def truncate_to_limits(text: str) -> str:
    """Truncate text to fit within limits.

    Args:
        text: Post text

    Returns:
        Truncated text
    """
    text = text.strip()

    # Truncate total length
    if len(text) > config.post_body_max_chars:
        # Try to cut at a sentence boundary
        truncated = text[: config.post_body_max_chars - 3]
        last_period = truncated.rfind(".")
        last_newline = truncated.rfind("\n")
        cut_point = max(last_period, last_newline)

        if cut_point > config.post_body_max_chars // 2:
            text = truncated[: cut_point + 1]
        else:
            text = truncated + "..."

    return text


def validate_and_suggest(text: str) -> tuple[bool, str, list[str]]:
    """Validate text and suggest fixes.

    Args:
        text: Post text to validate

    Returns:
        Tuple of (is_valid, fixed_text, list_of_suggestions)
    """
    result = lint_post(text)

    if result.passed:
        return True, text, []

    suggestions: list[str] = []
    fixed_text = text

    for violation in result.violations:
        if violation.rule == "double_blank":
            fixed_text = fix_common_issues(fixed_text)
            suggestions.append("Removed double blank lines")

        elif violation.rule == "body_length":
            fixed_text = truncate_to_limits(fixed_text)
            suggestions.append("Truncated to fit body limit")

        elif violation.rule == "hook_length":
            suggestions.append(
                f"Shorten first line to max {config.post_hook_max_chars} chars"
            )

        elif violation.rule == "max_lines":
            suggestions.append("Reduce to max 6 lines")

        elif violation.rule == "banned_word":
            word = violation.message.split("'")[1]
            suggestions.append(f"Remove or replace banned word: {word}")

        elif violation.rule == "spoiler_word":
            word = violation.message.split("'")[1]
            suggestions.append(f"Remove spoiler word: {word}")

    # Re-lint after fixes
    final_result = lint_post(fixed_text)

    return final_result.passed, fixed_text, suggestions
