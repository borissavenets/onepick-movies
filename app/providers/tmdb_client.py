"""TMDB API client with retry logic."""

import asyncio
from typing import Any, Literal

import httpx

from app.logging import get_logger

logger = get_logger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 5
BASE_BACKOFF = 1.0


# Combined movie + TV genre map (TMDB genre IDs -> English names)
TMDB_GENRE_MAP: dict[int, str] = {
    28: "Action",
    12: "Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    14: "Fantasy",
    36: "History",
    27: "Horror",
    10402: "Music",
    9648: "Mystery",
    10749: "Romance",
    878: "Science Fiction",
    10770: "TV Movie",
    53: "Thriller",
    10752: "War",
    37: "Western",
    # TV-specific
    10759: "Action & Adventure",
    10762: "Kids",
    10763: "News",
    10764: "Reality",
    10765: "Sci-Fi & Fantasy",
    10766: "Soap",
    10767: "Talk",
    10768: "War & Politics",
}


def genre_ids_to_names(genre_ids: list[int]) -> list[str]:
    """Convert TMDB genre IDs to human-readable names.

    Args:
        genre_ids: List of TMDB genre IDs

    Returns:
        List of genre name strings
    """
    return [TMDB_GENRE_MAP[gid] for gid in genre_ids if gid in TMDB_GENRE_MAP]


class TMDBError(Exception):
    """Base exception for TMDB API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class TMDBRateLimitError(TMDBError):
    """Rate limit exceeded."""

    def __init__(self, retry_after: int | None = None):
        super().__init__("Rate limit exceeded", status_code=429)
        self.retry_after = retry_after


class TMDBClient:
    """Async TMDB API client with retry logic."""

    def __init__(
        self,
        bearer_token: str,
        language: str = "en-US",
        region: str = "",
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """Initialize TMDB client.

        Args:
            bearer_token: TMDB API bearer token (v4 auth)
            language: Language for results (e.g., "en-US")
            region: Region for results (e.g., "US")
            timeout: Request timeout in seconds
        """
        self.bearer_token = bearer_token
        self.language = language
        self.region = region
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=TMDB_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.bearer_token}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an API request with retry logic.

        Args:
            method: HTTP method
            path: API path (e.g., "/trending/movie/day")
            params: Query parameters

        Returns:
            Parsed JSON response

        Raises:
            TMDBError: On API error after retries exhausted
        """
        client = await self._get_client()

        # Add default params
        if params is None:
            params = {}
        params.setdefault("language", self.language)
        if self.region:
            params.setdefault("region", self.region)

        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                response = await client.request(method, path, params=params)

                if response.status_code == 200:
                    return response.json()

                if response.status_code == 429:
                    # Rate limited
                    retry_after = response.headers.get("Retry-After")
                    wait_time = int(retry_after) if retry_after else (BASE_BACKOFF * (2 ** attempt))
                    logger.warning(
                        f"TMDB rate limited, retry after {wait_time}s "
                        f"(attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(wait_time)
                        continue
                    raise TMDBRateLimitError(retry_after=int(retry_after) if retry_after else None)

                if response.status_code >= 500:
                    # Server error, retry with backoff
                    wait_time = BASE_BACKOFF * (2 ** attempt)
                    logger.warning(
                        f"TMDB server error {response.status_code}, "
                        f"retry in {wait_time}s (attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(wait_time)
                        continue
                    raise TMDBError(
                        f"Server error: {response.status_code}",
                        status_code=response.status_code,
                    )

                # Client error (4xx except 429)
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("status_message", f"HTTP {response.status_code}")
                raise TMDBError(error_msg, status_code=response.status_code)

            except httpx.TimeoutException as e:
                wait_time = BASE_BACKOFF * (2 ** attempt)
                logger.warning(
                    f"TMDB timeout, retry in {wait_time}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES})"
                )
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(wait_time)
                    continue

            except httpx.RequestError as e:
                wait_time = BASE_BACKOFF * (2 ** attempt)
                logger.warning(
                    f"TMDB request error: {e}, retry in {wait_time}s "
                    f"(attempt {attempt + 1}/{MAX_RETRIES})"
                )
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(wait_time)
                    continue

        raise TMDBError(f"Max retries exceeded: {last_error}")

    async def fetch_trending(
        self,
        media_type: Literal["movie", "tv"],
        time_window: Literal["day", "week"] = "day",
        page: int = 1,
    ) -> dict[str, Any]:
        """Fetch trending movies or TV shows.

        Args:
            media_type: "movie" or "tv"
            time_window: "day" or "week"
            page: Page number (1-based)

        Returns:
            TMDB response with results array
        """
        path = f"/trending/{media_type}/{time_window}"
        return await self._request("GET", path, params={"page": page})

    async def fetch_popular(
        self,
        media_type: Literal["movie", "tv"],
        page: int = 1,
    ) -> dict[str, Any]:
        """Fetch popular movies or TV shows.

        Args:
            media_type: "movie" or "tv"
            page: Page number (1-based)

        Returns:
            TMDB response with results array
        """
        if media_type == "movie":
            path = "/movie/popular"
        else:
            path = "/tv/popular"
        return await self._request("GET", path, params={"page": page})

    async def fetch_top_rated(
        self,
        media_type: Literal["movie", "tv"],
        page: int = 1,
    ) -> dict[str, Any]:
        """Fetch top rated movies or TV shows.

        Args:
            media_type: "movie" or "tv"
            page: Page number (1-based)

        Returns:
            TMDB response with results array
        """
        if media_type == "movie":
            path = "/movie/top_rated"
        else:
            path = "/tv/top_rated"
        return await self._request("GET", path, params={"page": page})

    async def discover(
        self,
        media_type: Literal["movie", "tv"],
        page: int = 1,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Discover movies or TV shows with filters.

        Args:
            media_type: "movie" or "tv"
            page: Page number (1-based)
            params: Additional filter parameters (e.g., vote_count.gte, with_genres)

        Returns:
            TMDB response with results array
        """
        if media_type == "movie":
            path = "/discover/movie"
        else:
            path = "/discover/tv"

        request_params = {"page": page}
        if params:
            request_params.update(params)

        return await self._request("GET", path, params=request_params)

    async def fetch_upcoming(self, page: int = 1) -> dict[str, Any]:
        """Fetch upcoming movies.

        Args:
            page: Page number (1-based)

        Returns:
            TMDB response with results array
        """
        return await self._request("GET", "/movie/upcoming", params={"page": page})

    async def fetch_now_playing(self, page: int = 1) -> dict[str, Any]:
        """Fetch now playing movies.

        Args:
            page: Page number (1-based)

        Returns:
            TMDB response with results array
        """
        return await self._request("GET", "/movie/now_playing", params={"page": page})

    async def get_movie_details(self, movie_id: int) -> dict[str, Any]:
        """Get movie details.

        Args:
            movie_id: TMDB movie ID

        Returns:
            Movie details
        """
        return await self._request("GET", f"/movie/{movie_id}")

    async def get_tv_details(self, tv_id: int) -> dict[str, Any]:
        """Get TV show details.

        Args:
            tv_id: TMDB TV show ID

        Returns:
            TV show details
        """
        return await self._request("GET", f"/tv/{tv_id}")

    async def get_credits(
        self,
        media_type: Literal["movie", "tv"],
        tmdb_id: int,
    ) -> dict[str, Any]:
        """Get credits (cast + crew) for a movie or TV show.

        Args:
            media_type: "movie" or "tv"
            tmdb_id: TMDB ID

        Returns:
            Credits response with cast and crew arrays
        """
        return await self._request("GET", f"/{media_type}/{tmdb_id}/credits")
