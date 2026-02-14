"""TMDB catalog sync job."""

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from app.config import config
from app.logging import get_logger
from app.providers.tmdb_client import (
    TMDBClient,
    TMDBError,
    TMDBRateLimitError,
    genre_ids_to_names,
)
from app.storage import EventsRepo, ItemsRepo, get_session_factory

logger = get_logger(__name__)


@dataclass
class SyncStats:
    """Statistics from a sync run."""

    started_at: datetime
    finished_at: datetime | None = None
    total_fetched: int = 0
    total_upserted: int = 0
    errors: int = 0
    sources_processed: list[str] | None = None

    @property
    def duration_seconds(self) -> float:
        if self.finished_at is None:
            return 0.0
        return (self.finished_at - self.started_at).total_seconds()


def calculate_base_score(
    vote_average: float | None,
    vote_count: int | None,
    popularity: float | None,
) -> float:
    """Calculate base score from TMDB metrics.

    Formula: 0.5 * vote_average + 0.001 * vote_count + 0.01 * popularity

    Args:
        vote_average: TMDB vote average (0-10)
        vote_count: Number of votes
        popularity: TMDB popularity score

    Returns:
        Calculated base score
    """
    score = 0.0

    if vote_average is not None:
        score += 0.5 * vote_average

    if vote_count is not None:
        score += 0.001 * vote_count

    if popularity is not None:
        score += 0.01 * popularity

    return score


TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
MIN_VOTE_AVERAGE = 6.0  # Minimum rating to include


def extract_item_data(
    item: dict[str, Any],
    media_type: Literal["movie", "tv"],
) -> dict[str, Any] | None:
    """Extract normalized item data from TMDB response.

    Args:
        item: TMDB item dict
        media_type: "movie" or "tv"

    Returns:
        Normalized data dict or None if invalid or rating too low
    """
    tmdb_id = item.get("id")
    if not tmdb_id:
        return None

    # Filter by rating >= 6
    vote_average = item.get("vote_average")
    if vote_average is not None and vote_average < MIN_VOTE_AVERAGE:
        return None

    # Title differs between movies and TV
    if media_type == "movie":
        title = item.get("title") or item.get("original_title")
        release_date = item.get("release_date")
        item_type = "movie"
    else:
        title = item.get("name") or item.get("original_name")
        release_date = item.get("first_air_date")
        item_type = "series"

    if not title:
        return None

    # Build poster URL
    poster_path = item.get("poster_path")
    poster_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}" if poster_path else None

    # Convert genre IDs to names
    genre_ids = item.get("genre_ids", [])
    genre_names = genre_ids_to_names(genre_ids)

    return {
        "tmdb_id": tmdb_id,
        "title": title,
        "item_type": item_type,
        "overview": item.get("overview"),
        "release_date": release_date,
        "language": item.get("original_language"),
        "genre_ids": genre_ids,
        "genres_json": json.dumps(genre_names, ensure_ascii=False) if genre_names else None,
        "popularity": item.get("popularity"),
        "vote_average": vote_average,
        "vote_count": item.get("vote_count"),
        "poster_url": poster_url,
    }


async def fetch_source(
    client: TMDBClient,
    source_name: str,
    media_type: Literal["movie", "tv"],
    pages: int,
) -> list[dict[str, Any]]:
    """Fetch items from a specific source.

    Args:
        client: TMDB client
        source_name: Source identifier (trending_day, popular, top_rated, discover)
        media_type: "movie" or "tv"
        pages: Number of pages to fetch

    Returns:
        List of extracted item data dicts
    """
    items = []

    for page in range(1, pages + 1):
        try:
            if source_name == "trending_day":
                response = await client.fetch_trending(media_type, "day", page)
            elif source_name == "trending_week":
                response = await client.fetch_trending(media_type, "week", page)
            elif source_name == "popular":
                response = await client.fetch_popular(media_type, page)
            elif source_name == "top_rated":
                response = await client.fetch_top_rated(media_type, page)
            elif source_name == "upcoming":
                response = await client.fetch_upcoming(page)
            elif source_name == "now_playing":
                response = await client.fetch_now_playing(page)
            elif source_name == "discover":
                response = await client.discover(
                    media_type,
                    page,
                    params={"vote_count.gte": 200, "sort_by": "popularity.desc"},
                )
            else:
                logger.warning(f"Unknown source: {source_name}")
                continue

            results = response.get("results", [])
            for result in results:
                data = extract_item_data(result, media_type)
                if data:
                    items.append(data)

            logger.debug(
                f"Fetched {len(results)} {media_type}s from {source_name} page {page}"
            )

        except TMDBError as e:
            logger.error(f"Error fetching {source_name} {media_type} page {page}: {e}")
            break

    return items


def _extract_credits(credits_data: dict[str, Any]) -> dict[str, Any]:
    """Extract top 5 actors and director from TMDB credits response.

    Args:
        credits_data: TMDB credits API response

    Returns:
        Dict with 'director' and 'actors' keys
    """
    cast = credits_data.get("cast", [])
    crew = credits_data.get("crew", [])

    # Top 5 actors by order (cast is already sorted by order)
    actors = [member["name"] for member in cast[:5] if member.get("name")]

    # Director from crew
    director = None
    for member in crew:
        if member.get("job") == "Director" and member.get("name"):
            director = member["name"]
            break

    return {"director": director, "actors": actors}


async def _fetch_missing_credits(
    client: TMDBClient,
    items_repo: ItemsRepo,
    batch_size: int,
) -> int:
    """Fetch credits for items that don't have them yet.

    Args:
        client: TMDB client
        items_repo: Items repository
        batch_size: Max items to process per run

    Returns:
        Number of items updated
    """
    items = await items_repo.list_missing_credits(limit=batch_size)
    if not items:
        return 0

    logger.info(f"Fetching credits for {len(items)} items")
    updated = 0

    for item in items:
        # Extract TMDB ID and media type from item
        if not item.source_id:
            continue

        tmdb_id = int(item.source_id)
        media_type: Literal["movie", "tv"] = "movie" if item.type == "movie" else "tv"

        try:
            credits_data = await client.get_credits(media_type, tmdb_id)
            extracted = _extract_credits(credits_data)
            credits_json = json.dumps(extracted, ensure_ascii=False)
            await items_repo.update_credits(item.item_id, credits_json)
            updated += 1
        except TMDBRateLimitError:
            logger.warning("Credits fetch stopped: rate limit hit")
            break
        except TMDBError as e:
            logger.warning(f"Credits fetch failed for {item.item_id}: {e}")
            continue

    logger.info(f"Updated credits for {updated}/{len(items)} items")
    return updated


async def run_tmdb_sync() -> SyncStats:
    """Run TMDB catalog sync.

    Fetches trending, popular, and top-rated movies/TV from TMDB
    and upserts them into the items table.

    Returns:
        SyncStats with run statistics
    """
    stats = SyncStats(started_at=datetime.now(timezone.utc))

    if not config.tmdb_bearer_token:
        logger.warning("TMDB sync skipped: TMDB_BEARER_TOKEN not configured")
        stats.finished_at = datetime.now(timezone.utc)
        return stats

    if not config.tmdb_sync_enabled:
        logger.info("TMDB sync skipped: TMDB_SYNC_ENABLED=false")
        stats.finished_at = datetime.now(timezone.utc)
        return stats

    logger.info(
        f"Starting TMDB sync: pages={config.tmdb_pages_per_run}, "
        f"max_items={config.tmdb_max_items_per_run}"
    )

    # Log sync started event
    session_factory = get_session_factory()
    async with session_factory() as session:
        events_repo = EventsRepo(session)
        await events_repo.log_event(
            event_name="tmdb_sync_started",
            payload={
                "pages_per_run": config.tmdb_pages_per_run,
                "max_items_per_run": config.tmdb_max_items_per_run,
            },
        )

    client = TMDBClient(
        bearer_token=config.tmdb_bearer_token,
        language=config.tmdb_language,
        region=config.tmdb_region,
    )

    try:
        all_items: dict[int, dict[str, Any]] = {}  # Dedupe by tmdb_id
        sources_processed = []

        # Define sources to fetch
        sources = [
            ("trending_day", "movie"),
            ("trending_day", "tv"),
            ("trending_week", "movie"),
            ("trending_week", "tv"),
            ("popular", "movie"),
            ("popular", "tv"),
            ("top_rated", "movie"),
            ("top_rated", "tv"),
            ("upcoming", "movie"),
            ("now_playing", "movie"),
            ("discover", "movie"),
            ("discover", "tv"),
        ]

        for source_name, media_type in sources:
            source_label = f"{source_name}_{media_type}"
            logger.info(f"Fetching {source_label}...")

            items = await fetch_source(
                client,
                source_name,
                media_type,  # type: ignore
                config.tmdb_pages_per_run,
            )

            for item in items:
                tmdb_id = item["tmdb_id"]
                # Keep first occurrence (prioritize earlier sources)
                if tmdb_id not in all_items:
                    all_items[tmdb_id] = item

            sources_processed.append(source_label)
            stats.total_fetched += len(items)

            # Check max items limit
            if len(all_items) >= config.tmdb_max_items_per_run:
                logger.info(f"Reached max items limit ({config.tmdb_max_items_per_run})")
                break

        stats.sources_processed = sources_processed
        logger.info(f"Fetched {len(all_items)} unique items from TMDB")

        # Upsert items
        async with session_factory() as session:
            items_repo = ItemsRepo(session)

            upsert_count = 0
            for tmdb_id, item_data in all_items.items():
                if upsert_count >= config.tmdb_max_items_per_run:
                    break

                try:
                    await items_repo.upsert_tmdb_item(
                        tmdb_id=item_data["tmdb_id"],
                        item_type=item_data["item_type"],
                        title=item_data["title"],
                        overview=item_data.get("overview"),
                        genres=item_data.get("genre_ids"),
                        genres_json=item_data.get("genres_json"),
                        language=item_data.get("language"),
                        popularity=item_data.get("popularity"),
                        vote_average=item_data.get("vote_average"),
                        vote_count=item_data.get("vote_count"),
                        poster_url=item_data.get("poster_url"),
                    )
                    upsert_count += 1

                except Exception as e:
                    logger.error(f"Error upserting item {tmdb_id}: {e}")
                    stats.errors += 1

            stats.total_upserted = upsert_count
            logger.info(f"Upserted {upsert_count} items")

            # Incremental credits fetch for items missing credits_json
            if config.tmdb_credits_enabled:
                await _fetch_missing_credits(
                    client, items_repo, config.tmdb_credits_batch_size
                )

    except Exception as e:
        logger.exception(f"TMDB sync failed: {e}")
        stats.errors += 1

        # Log error event
        async with session_factory() as session:
            events_repo = EventsRepo(session)
            await events_repo.log_event(
                event_name="tmdb_sync_error",
                payload={
                    "error": str(e)[:500],  # Truncate for safety
                    "fetched": stats.total_fetched,
                    "upserted": stats.total_upserted,
                },
            )

    finally:
        await client.close()

    stats.finished_at = datetime.now(timezone.utc)

    # Log sync finished event
    async with session_factory() as session:
        events_repo = EventsRepo(session)
        await events_repo.log_event(
            event_name="tmdb_sync_finished",
            payload={
                "total_fetched": stats.total_fetched,
                "total_upserted": stats.total_upserted,
                "errors": stats.errors,
                "duration_seconds": stats.duration_seconds,
                "sources_processed": stats.sources_processed,
            },
        )

    logger.info(
        f"TMDB sync finished: fetched={stats.total_fetched}, "
        f"upserted={stats.total_upserted}, errors={stats.errors}, "
        f"duration={stats.duration_seconds:.1f}s"
    )

    return stats
