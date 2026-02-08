"""APScheduler configuration and job management."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore

from app.logging import get_logger

logger = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None

TMDB_SYNC_JOB_ID = "tmdb_sync"
PUBLISH_POST_JOB_ID = "publish_post"
BOT_CLICKS_JOB_ID = "bot_clicks_agg"
COMPUTE_SCORES_JOB_ID = "compute_scores"
AB_WINNER_JOB_ID = "ab_winner"
DAILY_METRICS_JOB_ID = "daily_metrics"
ALERT_CHECKS_JOB_ID = "alert_checks"


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the scheduler instance."""
    global _scheduler

    if _scheduler is None:
        logger.info("Creating scheduler")
        _scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 60,
            },
        )

    return _scheduler


def start_scheduler() -> None:
    """Start the scheduler if not already running."""
    scheduler = get_scheduler()
    if not scheduler.running:
        logger.info("Starting scheduler")
        scheduler.start()


def shutdown_scheduler() -> None:
    """Shutdown the scheduler gracefully."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        logger.info("Shutting down scheduler")
        _scheduler.shutdown(wait=True)
        _scheduler = None


def add_job(func, trigger: str, **kwargs) -> str:
    """Add a job to the scheduler."""
    scheduler = get_scheduler()
    job = scheduler.add_job(func, trigger, **kwargs)
    logger.info(f"Added job {job.id} with trigger {trigger}")
    return job.id


def remove_job(job_id: str) -> bool:
    """Remove a job from the scheduler."""
    scheduler = get_scheduler()
    try:
        scheduler.remove_job(job_id)
        logger.info(f"Removed job {job_id}")
        return True
    except Exception:
        logger.warning(f"Job {job_id} not found")
        return False


# ------------------------------------------------------------------
# Individual job setup helpers
# ------------------------------------------------------------------

def _remove_jobs_by_prefix(prefix: str) -> None:
    scheduler = get_scheduler()
    for job in scheduler.get_jobs():
        if job.id.startswith(prefix):
            try:
                scheduler.remove_job(job.id)
            except Exception:
                pass


def setup_tmdb_sync_job() -> str | None:
    """Setup the TMDB sync periodic job."""
    from app.config import config

    if not config.tmdb_sync_enabled:
        logger.info("TMDB sync job not scheduled: TMDB_SYNC_ENABLED=false")
        return None

    if not config.tmdb_bearer_token:
        logger.warning("TMDB sync job not scheduled: TMDB_BEARER_TOKEN not set")
        return None

    from app.jobs.tmdb_sync import run_tmdb_sync

    scheduler = get_scheduler()
    try:
        scheduler.remove_job(TMDB_SYNC_JOB_ID)
    except Exception:
        pass

    from datetime import datetime, timezone

    job = scheduler.add_job(
        run_tmdb_sync,
        "interval",
        hours=config.tmdb_sync_interval_hours,
        id=TMDB_SYNC_JOB_ID,
        name="TMDB Catalog Sync",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),
    )
    logger.info(
        f"Scheduled TMDB sync job: interval={config.tmdb_sync_interval_hours}h, "
        f"job_id={job.id}"
    )
    return job.id


def setup_publish_post_jobs() -> list[str]:
    """Setup channel publishing jobs.

    If ``POST_INTERVAL_MINUTES > 0`` a single interval trigger is used.
    Otherwise, registers one cron job per **unique time slot** across all
    schedule presets.  At runtime the publish job decides via bandit
    whether the current slot belongs to the active schedule.
    """
    from app.config import config

    if not config.channel_post_enabled:
        logger.info("Publish post jobs not scheduled: CHANNEL_POST_ENABLED=false")
        return []

    if not config.channel_id:
        logger.warning("Publish post jobs not scheduled: CHANNEL_ID not set")
        return []

    from app.jobs.publish_posts import run_publish_post
    from app.jobs.schedule_presets import get_all_unique_slots

    _remove_jobs_by_prefix(PUBLISH_POST_JOB_ID)
    scheduler = get_scheduler()
    job_ids: list[str] = []

    if config.post_interval_minutes > 0:
        job_id = f"{PUBLISH_POST_JOB_ID}_interval"
        scheduler.add_job(
            run_publish_post,
            "interval",
            minutes=config.post_interval_minutes,
            id=job_id,
            name="Channel Post (interval)",
            replace_existing=True,
            kwargs={"slot_index": 0, "slot_time": "interval"},
        )
        job_ids.append(job_id)
        logger.info(
            f"Scheduled publish_post: every {config.post_interval_minutes}m"
        )
    else:
        all_slots = get_all_unique_slots()
        for slot_index, slot_time in enumerate(all_slots):
            try:
                parts = slot_time.split(":")
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
            except (ValueError, IndexError):
                logger.warning(f"Invalid schedule slot: '{slot_time}', skipping")
                continue

            job_id = f"{PUBLISH_POST_JOB_ID}_{slot_index}"
            scheduler.add_job(
                run_publish_post,
                "cron",
                hour=hour,
                minute=minute,
                timezone=config.post_timezone,
                id=job_id,
                name=f"Channel Post ({slot_time})",
                replace_existing=True,
                kwargs={"slot_index": slot_index, "slot_time": slot_time},
            )
            job_ids.append(job_id)
            logger.info(
                f"Scheduled publish_post: slot {slot_index} at {slot_time} "
                f"tz={config.post_timezone}"
            )

        logger.info(
            f"Schedule bandit: registered {len(all_slots)} unique slots "
            f"from {len(get_all_unique_slots())} presets: {all_slots}"
        )

    return job_ids


def setup_bot_clicks_job() -> str:
    """Schedule hourly bot-click aggregation."""
    from app.jobs.bot_clicks_aggregator import run_bot_clicks_aggregator

    scheduler = get_scheduler()
    try:
        scheduler.remove_job(BOT_CLICKS_JOB_ID)
    except Exception:
        pass

    job = scheduler.add_job(
        run_bot_clicks_aggregator,
        "interval",
        hours=1,
        id=BOT_CLICKS_JOB_ID,
        name="Bot Clicks Aggregator",
        replace_existing=True,
    )
    logger.info(f"Scheduled bot_clicks_aggregator: hourly, job_id={job.id}")
    return job.id


def setup_compute_scores_job() -> str:
    """Schedule scoring every 6 hours."""
    from app.jobs.compute_scores import run_compute_scores

    scheduler = get_scheduler()
    try:
        scheduler.remove_job(COMPUTE_SCORES_JOB_ID)
    except Exception:
        pass

    job = scheduler.add_job(
        run_compute_scores,
        "interval",
        hours=6,
        id=COMPUTE_SCORES_JOB_ID,
        name="Compute Post Scores",
        replace_existing=True,
    )
    logger.info(f"Scheduled compute_scores: every 6h, job_id={job.id}")
    return job.id


def setup_ab_winner_job() -> str:
    """Schedule daily A/B winner selection (03:00 UTC)."""
    from app.jobs.ab_winner import run_ab_winner_selection

    scheduler = get_scheduler()
    try:
        scheduler.remove_job(AB_WINNER_JOB_ID)
    except Exception:
        pass

    job = scheduler.add_job(
        run_ab_winner_selection,
        "cron",
        hour=3,
        minute=0,
        id=AB_WINNER_JOB_ID,
        name="A/B Winner Selection",
        replace_existing=True,
    )
    logger.info(f"Scheduled ab_winner: daily 03:00 UTC, job_id={job.id}")
    return job.id


def setup_daily_metrics_job() -> str:
    """Schedule daily metrics computation (02:10 Europe/Kyiv)."""
    from app.observability.runner import run_daily_metrics

    scheduler = get_scheduler()
    try:
        scheduler.remove_job(DAILY_METRICS_JOB_ID)
    except Exception:
        pass

    from app.config import config

    job = scheduler.add_job(
        run_daily_metrics,
        "cron",
        hour=2,
        minute=10,
        timezone=config.post_timezone,
        id=DAILY_METRICS_JOB_ID,
        name="Daily Metrics Computation",
        replace_existing=True,
    )
    logger.info(f"Scheduled daily_metrics: 02:10 {config.post_timezone}, job_id={job.id}")
    return job.id


def setup_alert_checks_job() -> str:
    """Schedule alert checks every 6 hours."""
    from app.observability.runner import run_alert_checks

    scheduler = get_scheduler()
    try:
        scheduler.remove_job(ALERT_CHECKS_JOB_ID)
    except Exception:
        pass

    job = scheduler.add_job(
        run_alert_checks,
        "interval",
        hours=6,
        id=ALERT_CHECKS_JOB_ID,
        name="Alert Checks",
        replace_existing=True,
    )
    logger.info(f"Scheduled alert_checks: every 6h, job_id={job.id}")
    return job.id


# ------------------------------------------------------------------
# Aggregate setup
# ------------------------------------------------------------------

def setup_all_jobs() -> None:
    """Setup all scheduled jobs."""
    setup_tmdb_sync_job()
    setup_publish_post_jobs()
    setup_bot_clicks_job()
    setup_compute_scores_job()
    setup_ab_winner_job()
    setup_daily_metrics_job()
    setup_alert_checks_job()
    logger.info("All jobs configured")
