# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

OnePick Movies - Telegram bot + channel for movie/series recommendations in Ukrainian.
Stack: FastAPI + aiogram v3 + SQLAlchemy 2.0 async + SQLite (aiosqlite) + APScheduler.

## Commands

```bash
# Run bot (polling mode for dev)
python -m app.main polling

# Run bot (webhook mode, reads BOT_MODE from .env)
python -m app.main

# Run standalone scheduler (no bot)
python -m app.jobs

# Database migrations
alembic upgrade head

# Tests
pytest                                          # all tests
pytest app/tests/test_health.py                 # single file
pytest app/tests/test_health.py::test_health_endpoint  # single test

# Lint & format
ruff check .
ruff format .
```

## Architecture

### Entry Points
- `app/main.py` - FastAPI app with lifespan (DB init, scheduler start, webhook registration). Supports polling/webhook modes via `BOT_MODE` env var.
- `app/jobs/__main__.py` - Standalone scheduler runner (no bot, just background jobs).

### Layers

**Bot layer** (`app/bot/`) - aiogram v3 handlers organized in 5 routers wired in order (start > commands > flow > feedback > reactions). Callback data uses prefixes: `s:` state, `p:` pace, `f:` format, `a:` action, `r:` reason, `n:` navigation. User sessions are in-memory with TTL (flow: 10min, rec: 30min).

**Core layer** (`app/core/`) - Pure domain logic, no DB imports. Recommendation engine uses epsilon-greedy selection (70% exploit best score / 30% explore top-20). Scoring: `base_score + match_score(tags vs answers) + weight_bonus(user learning) + novelty_bonus(seeded random)`. Deterministic RNG per user/day/mode ensures stable results on refresh.

**Storage layer** (`app/storage/`) - SQLAlchemy 2.0 async with repository pattern. 11 ORM models, 13 repo classes. Session factory is a singleton via `get_session_factory()`. All repos take `AsyncSession` in constructor.

**Jobs layer** (`app/jobs/`) - APScheduler AsyncIOScheduler. 7 jobs: tmdb_sync (6h), publish_post (3 cron slots), bot_clicks_agg (1h), compute_scores (6h), ab_winner (daily 03:00 UTC), daily_metrics (02:00 UTC), alert_checks (30min).

**Content layer** (`app/content/`) - Template-based + LLM content generation with style validation (banned/spoiler word checks). A/B variant selection for channel posts.

**Providers** (`app/providers/`) - TMDB API client (httpx async). **LLM** (`app/llm/`) - Adapter pattern for OpenAI/Anthropic.

### Bot Question Flow
```
/start -> "Pick now" -> Q1 state (light/heavy/escape)
  -> Q2 pace (slow/fast) -> Q3 format (movie/series)
  -> get_recommendation() -> show result with action keyboard
  -> feedback (hit/miss/another/fav/share/seen) -> learning update
```

Callback data encodes previous answers: `f:movie|light|slow` carries state+pace as fallback.

### Key Patterns
- **Config**: Frozen dataclass `Config.from_env()` in `app/config.py`. 60+ env vars with defaults.
- **Logging**: Structured UTC ISO 8601 format. Use `get_logger(__name__)` per module.
- **Score formula**: `reactions*2 + forwards*3 + bot_clicks*4 - unsub_delta*5`
- **A/B testing**: Flip-flop with 15% margin, evaluated daily.
- **Anti-repeat**: 90-day exclusion window per user.
- **SQLite datetime caveat**: `_ensure_utc()` in compute_scores.py handles naive datetimes.
- **Admin API**: Token-based auth via `ADMIN_TOKEN` env var. Dashboard at `/admin/dashboard`.

## Testing

- pytest-asyncio with `asyncio_mode = "auto"`
- Test DB: `sqlite+aiosqlite:///./test_onepick.db` (via conftest.py)
- 3 known failing tests in test_bot_flow, test_credits, test_recommender (UA text assertion mismatches)

## Style

- Python 3.12+, ruff (line-length 100, rules: E, F, I, N, W)
- All text shown to users is in Ukrainian
- All DB operations are async, no blocking I/O
- Repos are stateless and session-scoped
