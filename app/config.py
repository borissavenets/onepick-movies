"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv

load_dotenv()


class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    """Application configuration."""

    # Bot settings
    bot_token: str
    bot_mode: Literal["webhook", "polling"]
    webhook_url: str | None
    webhook_path: str
    host: str
    port: int
    database_url: str
    admin_token: str | None
    log_level: str

    # TMDB settings
    tmdb_bearer_token: str | None
    tmdb_language: str
    tmdb_region: str
    tmdb_pages_per_run: int
    tmdb_max_items_per_run: int
    tmdb_sync_enabled: bool
    tmdb_sync_interval_hours: int
    tmdb_credits_enabled: bool
    tmdb_credits_batch_size: int

    # Recommendation settings
    recs_epsilon: float
    recs_max_candidates: int
    recs_anti_repeat_days: int
    recs_min_vote_count: int
    recs_prefer_curated: bool
    recs_require_tags: bool

    # OpenAI / LLM settings
    openai_api_key: str | None
    openai_model: str
    llm_enabled: bool
    anthropic_api_key: str | None
    anthropic_model: str
    llm_provider: str  # "openai" or "anthropic"

    # Channel settings
    channel_username: str
    bot_username: str
    cta_rate: float
    post_language: str
    post_hook_max_chars: int
    post_body_max_chars: int
    bot_rationale_max_chars: int
    post_repeat_avoidance_days: int

    # Channel auto-posting
    channel_id: str
    channel_post_enabled: bool
    post_slots: str
    post_timezone: str
    post_interval_minutes: int

    # Scoring & A/B
    score_window_hours: int
    ab_default_duration_days: int
    ab_eval_min_hours: int
    ab_eval_max_hours: int

    # Content constraints
    banned_words: list[str]
    spoiler_words: list[str]

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        bot_token = os.getenv("BOT_TOKEN")
        if not bot_token:
            raise ConfigurationError("BOT_TOKEN environment variable is required")

        bot_mode = os.getenv("BOT_MODE", "polling").lower()
        if bot_mode not in ("webhook", "polling"):
            raise ConfigurationError("BOT_MODE must be 'webhook' or 'polling'")

        webhook_url = os.getenv("WEBHOOK_URL")
        webhook_path = os.getenv("WEBHOOK_PATH", "/telegram/webhook")

        if bot_mode == "webhook" and not webhook_url:
            raise ConfigurationError("WEBHOOK_URL is required when BOT_MODE=webhook")

        host = os.getenv("HOST", "0.0.0.0")
        port_str = os.getenv("PORT", "8000")
        try:
            port = int(port_str)
        except ValueError:
            raise ConfigurationError(f"PORT must be an integer, got: {port_str}")

        database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./onepick.db")
        admin_token = os.getenv("ADMIN_TOKEN") or None
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()

        # TMDB settings
        tmdb_bearer_token = os.getenv("TMDB_BEARER_TOKEN") or None
        tmdb_language = os.getenv("TMDB_LANGUAGE", "en-US")
        tmdb_region = os.getenv("TMDB_REGION", "")

        tmdb_pages_str = os.getenv("TMDB_PAGES_PER_RUN", "3")
        try:
            tmdb_pages_per_run = int(tmdb_pages_str)
        except ValueError:
            tmdb_pages_per_run = 3

        tmdb_max_str = os.getenv("TMDB_MAX_ITEMS_PER_RUN", "500")
        try:
            tmdb_max_items_per_run = int(tmdb_max_str)
        except ValueError:
            tmdb_max_items_per_run = 500

        tmdb_sync_enabled = os.getenv("TMDB_SYNC_ENABLED", "true").lower() in ("true", "1", "yes")
        tmdb_credits_enabled = os.getenv("TMDB_CREDITS_ENABLED", "true").lower() in (
            "true", "1", "yes"
        )

        tmdb_credits_batch_str = os.getenv("TMDB_CREDITS_BATCH_SIZE", "20")
        try:
            tmdb_credits_batch_size = int(tmdb_credits_batch_str)
        except ValueError:
            tmdb_credits_batch_size = 20

        tmdb_interval_str = os.getenv("TMDB_SYNC_INTERVAL_HOURS", "6")
        try:
            tmdb_sync_interval_hours = int(tmdb_interval_str)
        except ValueError:
            tmdb_sync_interval_hours = 6

        # Recommendation settings
        recs_epsilon_str = os.getenv("RECS_EPSILON", "0.30")
        try:
            recs_epsilon = float(recs_epsilon_str)
        except ValueError:
            recs_epsilon = 0.30

        recs_max_candidates_str = os.getenv("RECS_MAX_CANDIDATES", "500")
        try:
            recs_max_candidates = int(recs_max_candidates_str)
        except ValueError:
            recs_max_candidates = 500

        recs_anti_repeat_days_str = os.getenv("RECS_ANTI_REPEAT_DAYS", "90")
        try:
            recs_anti_repeat_days = int(recs_anti_repeat_days_str)
        except ValueError:
            recs_anti_repeat_days = 90

        recs_min_vote_count_str = os.getenv("RECS_MIN_VOTE_COUNT", "200")
        try:
            recs_min_vote_count = int(recs_min_vote_count_str)
        except ValueError:
            recs_min_vote_count = 200

        recs_prefer_curated = os.getenv("RECS_PREFER_CURATED", "true").lower() in (
            "true",
            "1",
            "yes",
        )
        recs_require_tags = os.getenv("RECS_REQUIRE_TAGS", "false").lower() in (
            "true",
            "1",
            "yes",
        )

        # OpenAI / LLM settings
        openai_api_key = os.getenv("OPENAI_API_KEY") or None
        openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        llm_enabled = os.getenv("LLM_ENABLED", "true").lower() in ("true", "1", "yes")
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY") or None
        anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        llm_provider = os.getenv("LLM_PROVIDER", "anthropic" if anthropic_api_key else "openai")

        # Channel settings
        channel_username = os.getenv("CHANNEL_USERNAME", "OnePickMovies")
        bot_username = os.getenv("BOT_USERNAME", "onepick_movies_bot")

        cta_rate_str = os.getenv("CTA_RATE", "0.70")
        try:
            cta_rate = float(cta_rate_str)
        except ValueError:
            cta_rate = 0.70

        post_language = os.getenv("POST_LANGUAGE", "uk")

        post_hook_max_str = os.getenv("POST_HOOK_MAX_CHARS", "90")
        try:
            post_hook_max_chars = int(post_hook_max_str)
        except ValueError:
            post_hook_max_chars = 90

        post_body_max_str = os.getenv("POST_BODY_MAX_CHARS", "600")
        try:
            post_body_max_chars = int(post_body_max_str)
        except ValueError:
            post_body_max_chars = 600

        bot_rationale_max_str = os.getenv("BOT_RATIONALE_MAX_CHARS", "320")
        try:
            bot_rationale_max_chars = int(bot_rationale_max_str)
        except ValueError:
            bot_rationale_max_chars = 320

        post_repeat_days_str = os.getenv("POST_REPEAT_AVOIDANCE_DAYS", "60")
        try:
            post_repeat_avoidance_days = int(post_repeat_days_str)
        except ValueError:
            post_repeat_avoidance_days = 60

        # Channel auto-posting
        channel_id = os.getenv("CHANNEL_ID", "")
        channel_post_enabled = os.getenv("CHANNEL_POST_ENABLED", "true").lower() in (
            "true",
            "1",
            "yes",
        )
        post_slots = os.getenv("POST_SLOTS", "09:30,13:00,19:30")
        post_timezone = os.getenv("POST_TIMEZONE", "Europe/Kyiv")

        post_interval_str = os.getenv("POST_INTERVAL_MINUTES", "0")
        try:
            post_interval_minutes = int(post_interval_str)
        except ValueError:
            post_interval_minutes = 0

        # Scoring & A/B
        score_window_str = os.getenv("SCORE_WINDOW_HOURS", "36")
        try:
            score_window_hours = int(score_window_str)
        except ValueError:
            score_window_hours = 36

        ab_duration_str = os.getenv("AB_DEFAULT_DURATION_DAYS", "7")
        try:
            ab_default_duration_days = int(ab_duration_str)
        except ValueError:
            ab_default_duration_days = 7

        ab_min_str = os.getenv("AB_EVAL_MIN_HOURS", "24")
        try:
            ab_eval_min_hours = int(ab_min_str)
        except ValueError:
            ab_eval_min_hours = 24

        ab_max_str = os.getenv("AB_EVAL_MAX_HOURS", "48")
        try:
            ab_eval_max_hours = int(ab_max_str)
        except ValueError:
            ab_eval_max_hours = 48

        # Content constraints
        banned_words_str = os.getenv(
            "BANNED_WORDS",
            "топ,IMDb,рейтинг,найкращий,must-watch,шедевр"
        )
        banned_words = [w.strip().lower() for w in banned_words_str.split(",") if w.strip()]

        spoiler_words_str = os.getenv(
            "SPOILER_WORDS",
            "твіст,кінцівка,вбивця,помирає,вбивство,plot twist,ending,killer,dies,смерть,зрада"
        )
        spoiler_words = [w.strip().lower() for w in spoiler_words_str.split(",") if w.strip()]

        return cls(
            bot_token=bot_token,
            bot_mode=bot_mode,  # type: ignore[arg-type]
            webhook_url=webhook_url,
            webhook_path=webhook_path,
            host=host,
            port=port,
            database_url=database_url,
            admin_token=admin_token,
            log_level=log_level,
            tmdb_bearer_token=tmdb_bearer_token,
            tmdb_language=tmdb_language,
            tmdb_region=tmdb_region,
            tmdb_pages_per_run=tmdb_pages_per_run,
            tmdb_max_items_per_run=tmdb_max_items_per_run,
            tmdb_sync_enabled=tmdb_sync_enabled,
            tmdb_sync_interval_hours=tmdb_sync_interval_hours,
            tmdb_credits_enabled=tmdb_credits_enabled,
            tmdb_credits_batch_size=tmdb_credits_batch_size,
            recs_epsilon=recs_epsilon,
            recs_max_candidates=recs_max_candidates,
            recs_anti_repeat_days=recs_anti_repeat_days,
            recs_min_vote_count=recs_min_vote_count,
            recs_prefer_curated=recs_prefer_curated,
            recs_require_tags=recs_require_tags,
            openai_api_key=openai_api_key,
            openai_model=openai_model,
            llm_enabled=llm_enabled,
            anthropic_api_key=anthropic_api_key,
            anthropic_model=anthropic_model,
            llm_provider=llm_provider,
            channel_username=channel_username,
            bot_username=bot_username,
            cta_rate=cta_rate,
            post_language=post_language,
            post_hook_max_chars=post_hook_max_chars,
            post_body_max_chars=post_body_max_chars,
            bot_rationale_max_chars=bot_rationale_max_chars,
            post_repeat_avoidance_days=post_repeat_avoidance_days,
            channel_id=channel_id,
            channel_post_enabled=channel_post_enabled,
            post_slots=post_slots,
            post_timezone=post_timezone,
            post_interval_minutes=post_interval_minutes,
            score_window_hours=score_window_hours,
            ab_default_duration_days=ab_default_duration_days,
            ab_eval_min_hours=ab_eval_min_hours,
            ab_eval_max_hours=ab_eval_max_hours,
            banned_words=banned_words,
            spoiler_words=spoiler_words,
        )


config = Config.from_env()
