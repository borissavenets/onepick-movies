"""Repository for content item operations."""

import json
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.storage.heuristics import heuristic_tags
from app.storage.json_utils import safe_json_dumps
from app.storage.models import Item

logger = get_logger(__name__)


class ItemsRepo:
    """Repository for content item operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_item(self, item_id: str) -> Item | None:
        """Get item by ID.

        Args:
            item_id: Item ID

        Returns:
            Item instance or None
        """
        stmt = select(Item).where(Item.item_id == item_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_item_by_source(self, source: str, source_id: str) -> Item | None:
        """Get item by source and source_id.

        Args:
            source: Source identifier (e.g., 'tmdb', 'curated')
            source_id: Source-specific ID

        Returns:
            Item instance or None
        """
        stmt = select(Item).where(
            Item.source == source,
            Item.source_id == source_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_candidates(
        self,
        item_type: str | None = None,
        filter_tags: dict[str, Any] | None = None,
        exclude_ids: set[str] | None = None,
        curated_only: bool = False,
        source_preference: Literal["curated", "tmdb", "any"] | None = None,
        tag_status: str | None = None,
        limit: int = 200,
        randomize: bool = False,
    ) -> list[Item]:
        """List candidate items for recommendation.

        Args:
            item_type: Filter by type ('movie' or 'series')
            filter_tags: Tag filters (not implemented in SQLite, post-filter)
            exclude_ids: Item IDs to exclude
            curated_only: Only return curated items (legacy, prefer source_preference)
            source_preference: Filter by source ('curated', 'tmdb', or 'any')
            tag_status: Filter by tag_status ('pending', 'tagged', etc.)
            limit: Maximum items to return
            randomize: If True, fetch 3x limit and randomly sample to avoid
                       always picking the same top-scored items

        Returns:
            List of matching items
        """
        fetch_limit = limit * 3 if randomize else limit

        stmt = select(Item)

        if item_type:
            stmt = stmt.where(Item.type == item_type)

        # Handle source filtering
        if source_preference == "curated" or curated_only:
            stmt = stmt.where(Item.source == "curated")
        elif source_preference == "tmdb":
            stmt = stmt.where(Item.source == "tmdb")
        # 'any' or None means no source filter

        if tag_status:
            stmt = stmt.where(Item.tag_status == tag_status)

        if exclude_ids:
            stmt = stmt.where(Item.item_id.notin_(exclude_ids))

        stmt = stmt.order_by(Item.base_score.desc()).limit(fetch_limit)

        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        # Post-filter by tags if needed (SQLite doesn't support JSON queries well)
        if filter_tags:
            items = self._filter_by_tags(items, filter_tags)

        if randomize and len(items) > limit:
            items = random.sample(items, limit)

        return items

    def _filter_by_tags(
        self, items: list[Item], filter_tags: dict[str, Any]
    ) -> list[Item]:
        """Filter items by tag values (in-memory).

        Args:
            items: List of items to filter
            filter_tags: Tag key/value pairs to match

        Returns:
            Filtered list of items
        """
        filtered = []
        for item in items:
            try:
                tags = json.loads(item.tags_json)
            except (json.JSONDecodeError, TypeError):
                continue

            match = True
            for key, value in filter_tags.items():
                item_value = tags.get(key)
                if isinstance(value, list):
                    # Check if any tag value matches
                    if not isinstance(item_value, list):
                        match = False
                        break
                    if not any(v in item_value for v in value):
                        match = False
                        break
                else:
                    if item_value != value:
                        match = False
                        break

            if match:
                filtered.append(item)

        return filtered

    async def create_item(
        self,
        item_id: str,
        title: str,
        item_type: str,
        tags: dict[str, Any],
        language: str | None = None,
        base_score: float = 0.0,
        curated: bool = True,
        source: str = "curated",
        source_id: str | None = None,
        tag_status: str = "tagged",
    ) -> Item:
        """Create a new item.

        Args:
            item_id: Unique item ID
            title: Item title
            item_type: 'movie' or 'series'
            tags: Tag dictionary
            language: Optional language code
            base_score: Base recommendation score
            curated: Whether item is curated
            source: Source identifier
            source_id: Source-specific ID
            tag_status: Tag status ('pending', 'tagged', etc.)

        Returns:
            Created Item instance
        """
        now = datetime.now(timezone.utc)
        item = Item(
            item_id=item_id,
            title=title,
            type=item_type,
            tags_json=safe_json_dumps(tags),
            language=language,
            base_score=base_score,
            curated=curated,
            created_at=now,
            source=source,
            source_id=source_id,
            tag_status=tag_status,
            tag_version=1,
            updated_at=now,
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def upsert_tmdb_item(
        self,
        tmdb_id: int,
        item_type: str,
        title: str,
        overview: str | None = None,
        genres: list | None = None,
        language: str | None = None,
        popularity: float | None = None,
        vote_average: float | None = None,
        vote_count: int | None = None,
        poster_url: str | None = None,
        updated_at: datetime | None = None,
    ) -> Item:
        """Upsert a TMDB item (idempotent).

        Args:
            tmdb_id: TMDB ID
            item_type: 'movie' or 'series'
            title: Item title
            overview: Description/overview text
            genres: List of genres (strings, IDs, or dicts)
            language: Original language code
            popularity: TMDB popularity score
            vote_average: TMDB vote average (0-10)
            vote_count: Number of votes
            poster_url: Poster image URL
            updated_at: Last update timestamp

        Returns:
            Created or updated Item instance
        """
        now = updated_at or datetime.now(timezone.utc)
        source = "tmdb"
        source_id = str(tmdb_id)

        # Generate item_id for new items
        item_id = f"tmdb-{tmdb_id}"

        # Calculate base_score from TMDB data
        base_score = 0.0
        if popularity is not None:
            # Normalize popularity (typically 0-1000) to 0-5
            base_score = min(popularity / 200, 5.0)
        if vote_average is not None and vote_count is not None and vote_count > 100:
            # Blend with vote average (0-10 -> 0-5)
            vote_score = vote_average / 2
            base_score = (base_score + vote_score) / 2

        # Generate heuristic tags
        tags_json = heuristic_tags(
            genres=genres or [],
            overview=overview,
            vote_average=vote_average,
        )

        insert_stmt = sqlite_insert(Item).values(
            item_id=item_id,
            title=title,
            type=item_type,
            tags_json=tags_json,
            language=language,
            base_score=base_score,
            curated=False,
            created_at=now,
            source=source,
            source_id=source_id,
            tag_status="pending",
            tag_version=1,
            updated_at=now,
            poster_url=poster_url,
            vote_average=vote_average,
        )

        # On conflict with item_id (primary key), update fields
        # This works because item_id is deterministic: tmdb-{tmdb_id}
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["item_id"],
            set_={
                "title": title,
                "tags_json": tags_json,
                "language": language,
                "base_score": base_score,
                "updated_at": now,
                "poster_url": poster_url,
                "vote_average": vote_average,
            },
        )

        await self.session.execute(upsert_stmt)
        await self.session.commit()

        # Expire cached objects to get fresh data after upsert
        self.session.expire_all()

        # Return the item
        item = await self.get_item_by_source(source, source_id)
        if item is None:
            # Fallback to get by item_id
            item = await self.get_item(item_id)

        return item  # type: ignore

    async def seed_from_json(self, path: str = "items_seed/curated_items.json") -> int:
        """Seed items from JSON file (idempotent upsert).

        Sets source='curated', source_id=NULL, tag_status='tagged'.

        Args:
            path: Path to JSON file relative to project root

        Returns:
            Number of items processed
        """
        file_path = Path(path)
        if not file_path.exists():
            logger.warning(f"Seed file not found: {path}")
            return 0

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                items_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to read seed file: {e}")
            return 0

        if not isinstance(items_data, list):
            logger.error("Seed file must contain a JSON array")
            return 0

        now = datetime.now(timezone.utc)
        count = 0

        for item_data in items_data:
            item_id = item_data.get("item_id")
            if not item_id:
                logger.warning("Skipping item without item_id")
                continue

            tags = item_data.get("tags", {})
            tags_json = safe_json_dumps(tags)

            insert_stmt = sqlite_insert(Item).values(
                item_id=item_id,
                title=item_data.get("title", "Untitled"),
                type=item_data.get("type", "movie"),
                tags_json=tags_json,
                language=item_data.get("language"),
                base_score=item_data.get("base_score", 0.0),
                curated=item_data.get("curated", True),
                created_at=now,
                source="curated",
                source_id=None,
                tag_status="tagged",
                tag_version=1,
                updated_at=now,
            )
            # On conflict, update everything except item_id, created_at, source, source_id
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=["item_id"],
                set_={
                    "title": item_data.get("title", "Untitled"),
                    "type": item_data.get("type", "movie"),
                    "tags_json": tags_json,
                    "language": item_data.get("language"),
                    "base_score": item_data.get("base_score", 0.0),
                    "curated": item_data.get("curated", True),
                    "tag_status": "tagged",
                    "updated_at": now,
                },
            )
            await self.session.execute(upsert_stmt)
            count += 1

        await self.session.commit()
        logger.info(f"Seeded {count} items from {path}")
        return count

    async def count_items(self, source: str | None = None) -> int:
        """Count items in database.

        Args:
            source: Optional source filter

        Returns:
            Item count
        """
        stmt = select(func.count()).select_from(Item)

        if source:
            stmt = stmt.where(Item.source == source)

        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def list_pending_tags(self, limit: int = 100) -> list[Item]:
        """List items with pending tag status.

        Args:
            limit: Maximum items to return

        Returns:
            List of items needing tagging
        """
        stmt = (
            select(Item)
            .where(Item.tag_status == "pending")
            .order_by(Item.base_score.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_tags(
        self,
        item_id: str,
        tags_json: str,
        tag_status: str = "tagged",
        tag_version: int | None = None,
    ) -> bool:
        """Update item tags.

        Args:
            item_id: Item ID
            tags_json: New tags JSON string
            tag_status: New tag status
            tag_version: New tag version (increments if None)

        Returns:
            True if updated, False if not found
        """
        from sqlalchemy import update

        now = datetime.now(timezone.utc)

        stmt = (
            update(Item)
            .where(Item.item_id == item_id)
            .values(
                tags_json=tags_json,
                tag_status=tag_status,
                tag_version=Item.tag_version + 1 if tag_version is None else tag_version,
                updated_at=now,
            )
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0
