"""Repository for alert operations."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import Alert


class AlertsRepo:
    """Repository for observability alerts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
    ) -> Alert:
        """Create a new alert.

        Args:
            alert_type: Alert type identifier (e.g. TTFR_P90_HIGH)
            severity: info, warning, or critical
            message: Human-readable alert message

        Returns:
            Created Alert instance
        """
        now = datetime.now(timezone.utc)
        alert = Alert(
            alert_type=alert_type,
            severity=severity,
            message=message,
            created_at=now,
        )
        self.session.add(alert)
        await self.session.commit()
        await self.session.refresh(alert)
        return alert

    async def list_alerts(
        self,
        alert_type: str | None = None,
        unresolved_only: bool = False,
        limit: int = 50,
    ) -> list[Alert]:
        """List alerts with optional filters.

        Args:
            alert_type: Filter by alert type
            unresolved_only: Only return unresolved alerts
            limit: Maximum alerts to return

        Returns:
            List of Alert instances
        """
        stmt = select(Alert)

        if alert_type:
            stmt = stmt.where(Alert.alert_type == alert_type)

        if unresolved_only:
            stmt = stmt.where(Alert.resolved_at.is_(None))

        stmt = stmt.order_by(Alert.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def resolve_alert(self, alert_id: int) -> bool:
        """Mark an alert as resolved.

        Args:
            alert_id: Alert ID

        Returns:
            True if resolved, False if not found
        """
        stmt = select(Alert).where(Alert.id == alert_id)
        result = await self.session.execute(stmt)
        alert = result.scalar_one_or_none()

        if not alert:
            return False

        alert.resolved_at = datetime.now(timezone.utc)
        await self.session.commit()
        return True

    async def has_recent_alert(
        self,
        alert_type: str,
        hours: int = 24,
    ) -> bool:
        """Check if there's an unresolved alert of this type within recent hours.

        Args:
            alert_type: Alert type to check
            hours: Look-back window in hours

        Returns:
            True if a recent unresolved alert exists
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = (
            select(Alert)
            .where(
                Alert.alert_type == alert_type,
                Alert.resolved_at.is_(None),
                Alert.created_at >= cutoff,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None
