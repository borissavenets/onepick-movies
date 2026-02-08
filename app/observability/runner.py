"""Observability runner jobs.

- ``run_daily_metrics``: Computes all daily KPIs and persists to daily_metrics.
- ``run_alert_checks``: Evaluates alert conditions and creates alerts.
"""

from datetime import datetime, timedelta, timezone

from app.logging import get_logger

logger = get_logger(__name__)

# Alert thresholds
TTFR_P90_THRESHOLD_SECONDS = 30.0
HIT_RATE_MIN_THRESHOLD = 0.20
NO_POSTS_HOURS = 24
NO_TMDB_SYNC_HOURS = 48


async def run_daily_metrics(date_str: str | None = None) -> dict:
    """Compute and persist all daily metrics.

    Runs bot_metrics, channel_metrics, system_metrics, and TTFR SLO,
    then upserts each value into daily_metrics table.

    Args:
        date_str: Target date (YYYY-MM-DD). Defaults to yesterday.

    Returns:
        Summary dict with total metrics persisted.
    """
    from app.observability.bot_metrics import compute_bot_metrics
    from app.observability.channel_metrics import compute_channel_metrics
    from app.observability.slo import compute_ttfr
    from app.observability.system_metrics import compute_system_metrics
    from app.storage import DailyMetricsRepo, get_session_factory

    if date_str is None:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")

    all_metrics: dict[str, float] = {}

    # Compute all metric groups
    try:
        bot = await compute_bot_metrics(date_str)
        all_metrics.update(bot)
    except Exception as e:
        logger.error(f"Failed to compute bot metrics: {e}")

    try:
        channel = await compute_channel_metrics(date_str)
        all_metrics.update(channel)
    except Exception as e:
        logger.error(f"Failed to compute channel metrics: {e}")

    try:
        system = await compute_system_metrics()
        all_metrics.update(system)
    except Exception as e:
        logger.error(f"Failed to compute system metrics: {e}")

    try:
        ttfr = await compute_ttfr(date_str)
        all_metrics["slo_ttfr_p50"] = ttfr["p50"]
        all_metrics["slo_ttfr_p90"] = ttfr["p90"]
        all_metrics["slo_ttfr_samples"] = float(ttfr["sample_count"])
    except Exception as e:
        logger.error(f"Failed to compute TTFR: {e}")

    # Persist all metrics
    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = DailyMetricsRepo(session)
        for name, value in all_metrics.items():
            await repo.upsert_metric(date=date_str, metric_name=name, value=value)

    logger.info(f"Daily metrics {date_str}: persisted {len(all_metrics)} metrics")

    return {"date": date_str, "metrics_count": len(all_metrics), "metrics": all_metrics}


async def run_alert_checks() -> dict:
    """Evaluate alert conditions and create alerts if thresholds are breached.

    Alert conditions:
        - TTFR_P90_HIGH: TTFR p90 > 30 seconds
        - HIT_RATE_LOW: hit_rate < 20%
        - NO_POSTS_24H: no posts published in last 24 hours
        - NO_TMDB_SYNC_48H: no TMDB sync in last 48 hours

    Returns:
        Summary dict with alerts_created count.
    """
    from app.storage import AlertsRepo, DailyMetricsRepo, get_session_factory

    session_factory = get_session_factory()
    alerts_created = 0

    async with session_factory() as session:
        metrics_repo = DailyMetricsRepo(session)
        alerts_repo = AlertsRepo(session)

        # Check TTFR p90
        ttfr_p90 = await metrics_repo.get_latest("slo_ttfr_p90")
        if ttfr_p90 and ttfr_p90.value > TTFR_P90_THRESHOLD_SECONDS:
            if not await alerts_repo.has_recent_alert("TTFR_P90_HIGH", hours=24):
                await alerts_repo.add_alert(
                    alert_type="TTFR_P90_HIGH",
                    severity="warning",
                    message=(
                        f"TTFR p90 is {ttfr_p90.value:.1f}s "
                        f"(threshold: {TTFR_P90_THRESHOLD_SECONDS}s) "
                        f"on {ttfr_p90.date}"
                    ),
                )
                alerts_created += 1

        # Check hit rate
        hit_rate = await metrics_repo.get_latest("bot_hit_rate")
        samples = await metrics_repo.get_latest("bot_sessions")
        if (
            hit_rate
            and samples
            and samples.value >= 10  # need minimum sample size
            and hit_rate.value < HIT_RATE_MIN_THRESHOLD
        ):
            if not await alerts_repo.has_recent_alert("HIT_RATE_LOW", hours=24):
                await alerts_repo.add_alert(
                    alert_type="HIT_RATE_LOW",
                    severity="warning",
                    message=(
                        f"Hit rate is {hit_rate.value:.1%} "
                        f"(threshold: {HIT_RATE_MIN_THRESHOLD:.0%}) "
                        f"on {hit_rate.date}"
                    ),
                )
                alerts_created += 1

        # Check no posts in 24h
        last_post_age = await metrics_repo.get_latest("sys_last_post_age_hours")
        if last_post_age and last_post_age.value > NO_POSTS_HOURS:
            if not await alerts_repo.has_recent_alert("NO_POSTS_24H", hours=24):
                await alerts_repo.add_alert(
                    alert_type="NO_POSTS_24H",
                    severity="critical",
                    message=(
                        f"No posts published in {last_post_age.value:.0f} hours "
                        f"(threshold: {NO_POSTS_HOURS}h)"
                    ),
                )
                alerts_created += 1

        # Check no TMDB sync in 48h
        last_sync_age = await metrics_repo.get_latest("sys_last_tmdb_sync_age_hours")
        if last_sync_age and last_sync_age.value > NO_TMDB_SYNC_HOURS:
            if not await alerts_repo.has_recent_alert("NO_TMDB_SYNC_48H", hours=48):
                await alerts_repo.add_alert(
                    alert_type="NO_TMDB_SYNC_48H",
                    severity="warning",
                    message=(
                        f"No TMDB sync in {last_sync_age.value:.0f} hours "
                        f"(threshold: {NO_TMDB_SYNC_HOURS}h)"
                    ),
                )
                alerts_created += 1

    logger.info(f"Alert checks: {alerts_created} alerts created")
    return {"alerts_created": alerts_created}
