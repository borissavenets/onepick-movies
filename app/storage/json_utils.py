"""Safe JSON utilities that never throw exceptions."""

import json
from typing import Any

from app.logging import get_logger

logger = get_logger(__name__)


def safe_json_dumps(data: Any, default: str = "{}") -> str:
    """Serialize data to JSON string, returning default on failure.

    Args:
        data: Data to serialize
        default: Default string to return on failure

    Returns:
        JSON string or default value
    """
    if data is None:
        return default

    try:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError, OverflowError) as e:
        logger.warning(f"Failed to serialize JSON: {e}")
        return default


def safe_json_loads(text: str | None, default: dict | list | None = None) -> Any:
    """Parse JSON string, returning default on failure.

    Args:
        text: JSON string to parse
        default: Default value to return on failure (defaults to empty dict)

    Returns:
        Parsed data or default value
    """
    if default is None:
        default = {}

    if not text:
        return default

    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"Failed to parse JSON: {e}")
        return default
