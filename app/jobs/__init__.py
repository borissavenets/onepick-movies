"""Jobs module for scheduled tasks and background processing."""

from app.jobs.ab_winner import run_ab_winner_selection
from app.jobs.bot_clicks_aggregator import run_bot_clicks_aggregator
from app.jobs.channel_posting import run_channel_post, PostResult
from app.jobs.compute_scores import run_compute_scores, calculate_score
from app.jobs.publish_posts import run_publish_post
from app.jobs.publish_posts import PostResult as PublishPostResult
from app.jobs.scheduler import (
    add_job,
    get_scheduler,
    remove_job,
    setup_all_jobs,
    setup_publish_post_jobs,
    setup_tmdb_sync_job,
    setup_daily_metrics_job,
    setup_alert_checks_job,
    shutdown_scheduler,
    start_scheduler,
)
from app.jobs.tmdb_sync import run_tmdb_sync, SyncStats

__all__ = [
    "add_job",
    "calculate_score",
    "get_scheduler",
    "remove_job",
    "run_ab_winner_selection",
    "run_bot_clicks_aggregator",
    "run_channel_post",
    "run_compute_scores",
    "run_publish_post",
    "run_tmdb_sync",
    "setup_all_jobs",
    "setup_publish_post_jobs",
    "setup_tmdb_sync_job",
    "setup_daily_metrics_job",
    "setup_alert_checks_job",
    "shutdown_scheduler",
    "start_scheduler",
    "PostResult",
    "PublishPostResult",
    "SyncStats",
]
