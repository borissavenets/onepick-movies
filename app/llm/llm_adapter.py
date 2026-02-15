"""LLM adapter for text generation — supports OpenAI and Anthropic APIs."""

import asyncio
from typing import Any

import httpx

from app.config import config
from app.logging import get_logger

logger = get_logger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_TIMEOUT = 60.0
MAX_RETRIES = 3
BASE_BACKOFF = 1.0


class LLMDisabledError(Exception):
    """Raised when LLM is disabled but generation is attempted."""

    pass


class OpenAIError(Exception):
    """Base exception for LLM API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class OpenAIRateLimitError(OpenAIError):
    """Rate limit exceeded."""

    def __init__(self, retry_after: int | None = None):
        super().__init__("Rate limit exceeded", status_code=429)
        self.retry_after = retry_after


async def _call_openai(
    client: httpx.AsyncClient,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """Call OpenAI-compatible API."""
    headers = {
        "Authorization": f"Bearer {config.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.openai_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    response = await client.post(OPENAI_API_URL, headers=headers, json=payload)

    if response.status_code == 200:
        data = response.json()
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            logger.debug(
                f"OpenAI tokens: {data.get('usage', {}).get('total_tokens', 'N/A')}"
            )
            return content.strip()
        raise OpenAIError("Empty response from OpenAI")

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        raise OpenAIRateLimitError(
            retry_after=int(retry_after) if retry_after else None
        )

    if response.status_code >= 500:
        raise OpenAIError(
            f"Server error: {response.status_code}",
            status_code=response.status_code,
        )

    try:
        error_data = response.json()
        error_msg = error_data.get("error", {}).get(
            "message", f"HTTP {response.status_code}"
        )
    except Exception:
        error_msg = f"HTTP {response.status_code}"

    raise OpenAIError(error_msg, status_code=response.status_code)


async def _call_anthropic(
    client: httpx.AsyncClient,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """Call Anthropic Messages API."""
    headers = {
        "x-api-key": config.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.anthropic_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
    }

    response = await client.post(ANTHROPIC_API_URL, headers=headers, json=payload)

    if response.status_code == 200:
        data = response.json()
        content_blocks = data.get("content", [])
        text_parts = [
            block.get("text", "")
            for block in content_blocks
            if block.get("type") == "text"
        ]
        result = "\n".join(text_parts).strip()
        usage = data.get("usage", {})
        logger.debug(
            f"Anthropic tokens: in={usage.get('input_tokens', '?')}, "
            f"out={usage.get('output_tokens', '?')}"
        )
        return result

    if response.status_code == 429:
        retry_after = response.headers.get("retry-after")
        raise OpenAIRateLimitError(
            retry_after=int(retry_after) if retry_after else None
        )

    if response.status_code >= 500:
        raise OpenAIError(
            f"Anthropic server error: {response.status_code}",
            status_code=response.status_code,
        )

    try:
        error_data = response.json()
        error_msg = error_data.get("error", {}).get(
            "message", f"HTTP {response.status_code}"
        )
    except Exception:
        error_msg = f"HTTP {response.status_code}"

    raise OpenAIError(error_msg, status_code=response.status_code)


async def generate_text(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 500,
    temperature: float = 0.7,
) -> str:
    """Generate text using configured LLM provider.

    Args:
        system_prompt: System instructions for the model
        user_prompt: User message/request
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature

    Returns:
        Generated text

    Raises:
        LLMDisabledError: If LLM is disabled in config
        OpenAIError: On API error after retries exhausted
    """
    if not config.llm_enabled:
        raise LLMDisabledError("LLM is disabled in configuration")

    provider = config.llm_provider

    if provider == "anthropic":
        if not config.anthropic_api_key:
            raise LLMDisabledError("ANTHROPIC_API_KEY is not configured")
        call_fn = _call_anthropic
        provider_label = f"Anthropic/{config.anthropic_model}"
    else:
        if not config.openai_api_key:
            raise LLMDisabledError("OPENAI_API_KEY is not configured")
        call_fn = _call_openai
        provider_label = f"OpenAI/{config.openai_model}"

    last_error: Exception | None = None

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        for attempt in range(MAX_RETRIES):
            try:
                result = await call_fn(
                    client, system_prompt, user_prompt, max_tokens, temperature
                )
                return result

            except OpenAIRateLimitError as e:
                wait_time = e.retry_after or (BASE_BACKOFF * (2 ** attempt))
                logger.warning(
                    f"{provider_label} rate limited, retry after {wait_time}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES})"
                )
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(wait_time)
                    continue

            except OpenAIError as e:
                if e.status_code and e.status_code >= 500:
                    wait_time = BASE_BACKOFF * (2 ** attempt)
                    logger.warning(
                        f"{provider_label} server error, retry in {wait_time}s "
                        f"(attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    last_error = e
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(wait_time)
                        continue
                raise

            except httpx.TimeoutException as e:
                wait_time = BASE_BACKOFF * (2 ** attempt)
                logger.warning(
                    f"{provider_label} timeout, retry in {wait_time}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES})"
                )
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(wait_time)
                    continue

            except httpx.RequestError as e:
                wait_time = BASE_BACKOFF * (2 ** attempt)
                logger.warning(
                    f"{provider_label} request error: {e}, retry in {wait_time}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES})"
                )
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(wait_time)
                    continue

            except (LLMDisabledError,):
                raise

            except Exception as e:
                logger.exception(f"Unexpected {provider_label} error: {e}")
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(BASE_BACKOFF * (2 ** attempt))
                    continue

    raise OpenAIError(f"Max retries exceeded ({provider_label}): {last_error}")
