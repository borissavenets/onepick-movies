"""Repository for daily metrics operations."""

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import DailyMetric


class DailyMetricsRepo:
    """Repository for daily aggregated metrics."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_metric(
        self,
        date: str,
        metric_name: str,
        value: float,
    ) -> DailyMetric:
        """Insert or update a daily metric.

        Args:
            date: Date string (YYYY-MM-DD)
            metric_name: Metric name
            value: Metric value

        Returns:
            DailyMetric instance
        """
        now = datetime.now(timezone.utc)

        stmt = select(DailyMetric).where(
            DailyMetric.date == date,
            DailyMetric.metric_name == metric_name,
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.value = value
            existing.updated_at = now
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        metric = DailyMetric(
            date=date,
            metric_name=metric_name,
            value=value,
            updated_at=now,
        )
        self.session.add(metric)
        await self.session.commit()
        await self.session.refresh(metric)
        return metric

    async def get_metric(
        self,
        date: str,
        metric_name: str,
    ) -> DailyMetric | None:
        """Get a specific daily metric.

        Args:
            date: Date string (YYYY-MM-DD)
            metric_name: Metric name

        Returns:
            DailyMetric or None
        """
        stmt = select(DailyMetric).where(
            DailyMetric.date == date,
            DailyMetric.metric_name == metric_name,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_metrics(
        self,
        metric_name: str | None = None,
        days: int = 30,
    ) -> list[DailyMetric]:
        """List daily metrics, optionally filtered by name.

        Args:
            metric_name: Optional filter by metric name
            days: Number of days to look back

        Returns:
            List of DailyMetric instances
        """
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        stmt = select(DailyMetric).where(DailyMetric.date >= cutoff)

        if metric_name:
            stmt = stmt.where(DailyMetric.metric_name == metric_name)

        stmt = stmt.order_by(DailyMetric.date.desc(), DailyMetric.metric_name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest(
        self,
        metric_name: str,
    ) -> DailyMetric | None:
        """Get the most recent value for a metric.

        Args:
            metric_name: Metric name

        Returns:
            DailyMetric or None
        """
        stmt = (
            select(DailyMetric)
            .where(DailyMetric.metric_name == metric_name)
            .order_by(DailyMetric.date.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_date(self, date: str) -> list[DailyMetric]:
        """List all metrics for a specific date.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            List of DailyMetric instances
        """
        stmt = (
            select(DailyMetric)
            .where(DailyMetric.date == date)
            .order_by(DailyMetric.metric_name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
