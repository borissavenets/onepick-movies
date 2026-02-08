"""LLM adapter for external AI service integration."""

from typing import Any

import httpx

from app.logging import get_logger

logger = get_logger(__name__)


class LLMAdapter:
    """Adapter for LLM API calls using httpx.

    This adapter provides a clean interface for making requests to
    LLM services with proper error handling and logging.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the LLM adapter.

        Args:
            base_url: Base URL for the LLM API
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )

        return self._client

    async def complete(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> str | None:
        """Send a completion request to the LLM.

        Args:
            prompt: The prompt text to complete
            **kwargs: Additional parameters for the API

        Returns:
            The completion text, or None if the request failed
        """
        client = await self._get_client()

        payload = {
            "prompt": prompt,
            **kwargs,
        }

        try:
            response = await client.post("/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("text") or data.get("completion")

        except httpx.HTTPStatusError as e:
            logger.error(f"LLM API error: {e.response.status_code} - {e.response.text}")
            return None

        except httpx.RequestError as e:
            logger.error(f"LLM request error: {e}")
            return None

        except Exception as e:
            logger.exception(f"Unexpected LLM error: {e}")
            return None

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("LLM adapter client closed")
