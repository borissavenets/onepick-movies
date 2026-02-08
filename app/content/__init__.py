"""Content module for channel post generation and curation."""

from app.content.generator import GeneratedPost, generate_post
from app.content.selector import SelectedItem, select_for_fact, select_for_if_liked, select_for_one_pick
from app.content.style_lint import LintResult, LintViolation, lint_post
from app.content.templates import FORMATS, PostFormat, get_all_formats, get_format, render_fallback

__all__ = [
    # Generator
    "GeneratedPost",
    "generate_post",
    # Selector
    "SelectedItem",
    "select_for_one_pick",
    "select_for_if_liked",
    "select_for_fact",
    # Style lint
    "LintResult",
    "LintViolation",
    "lint_post",
    # Templates
    "FORMATS",
    "PostFormat",
    "get_format",
    "get_all_formats",
    "render_fallback",
]
