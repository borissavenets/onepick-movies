# OnePick Movies

Telegram bot for content curation and channel posting.

## Stack

- **FastAPI** - HTTP server for webhooks
- **aiogram v3** - Telegram Bot API framework
- **SQLite** - Database (MVP)
- **SQLAlchemy 2.0** - ORM with async support
- **Alembic** - Database migrations
- **APScheduler** - Scheduled jobs
- **httpx** - Async HTTP client

## Local Setup

### 1. Create Virtual Environment

```bash
cd onepick
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -e ".[dev]"
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set your `BOT_TOKEN` from [@BotFather](https://t.me/BotFather).

### 4. Run Database Migrations

```bash
# Apply all migrations
alembic upgrade head
```

### 5. Seed Initial Data

```python
# In Python or via script
import asyncio
from app.storage import get_session_factory, ItemsRepo

async def seed():
    factory = get_session_factory()
    async with factory() as session:
        repo = ItemsRepo(session)
        count = await repo.seed_from_json("items_seed/curated_items.json")
        print(f"Seeded {count} items")

asyncio.run(seed())
```

Or run the bot - seeding can be triggered at startup.

### 6. Run the Bot

#### Polling Mode (Development)

```bash
python -m app.main polling
```

Or simply (when BOT_MODE=polling in .env):

```bash
python -m app.main
```

#### Webhook Mode (Production)

Set in `.env`:
```
BOT_MODE=webhook
WEBHOOK_URL=https://your-domain.com
```

Then run:
```bash
python -m app.main
```

The server will:
1. Start FastAPI on the configured host/port
2. Register the webhook with Telegram
3. Accept incoming updates at `POST /telegram/webhook`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check, returns `{"ok": true}` |
| POST | `/telegram/webhook` | Telegram webhook endpoint (webhook mode only) |

## Project Structure

```
onepick/
├── app/
│   ├── main.py              # Application entrypoint
│   ├── config.py            # Configuration from env vars
│   ├── logging.py           # Structured logging setup
│   ├── bot/                 # Telegram bot handlers
│   │   ├── router.py        # Router wiring
│   │   ├── handlers_*.py    # Command/message handlers
│   │   ├── keyboards.py     # Inline/reply keyboards
│   │   ├── messages.py      # Message templates
│   │   └── sender.py        # Safe message sending
│   ├── core/                # Domain contracts
│   ├── content/             # Content management
│   ├── storage/             # Database layer
│   │   ├── models.py        # SQLAlchemy ORM models
│   │   ├── db.py            # Engine/session factory
│   │   ├── json_utils.py    # Safe JSON helpers
│   │   └── repo_*.py        # Repository classes
│   ├── jobs/                # Scheduled tasks
│   ├── observability/       # Metrics/monitoring
│   ├── llm/                 # AI integrations
│   └── tests/               # Test suite
├── items_seed/              # Seed data
│   └── curated_items.json   # Initial content items
├── alembic/                 # Database migrations
│   ├── env.py               # Async migration env
│   └── versions/            # Migration scripts
├── pyproject.toml
├── alembic.ini
└── .env.example
```

## Database Schema

### Tables

| Table | Description |
|-------|-------------|
| `users` | User profiles and activity tracking |
| `user_weights` | Personalization weights per user |
| `items` | Content items (movies, series) |
| `recommendations` | Recommendation records |
| `feedback` | User feedback on recommendations |
| `favorites` | User favorites |
| `posts` | Channel posts with A/B variants |
| `post_metrics` | Metrics snapshots for posts |
| `ab_winners` | A/B test winner locks |
| `events` | Event logging for analytics |

### Repositories

Each table has a corresponding async repository:

- `UsersRepo` - User CRUD, reset preferences
- `WeightsRepo` - Get/set preference weights
- `ItemsRepo` - Item queries, seeding
- `RecsRepo` - Create/list recommendations
- `FeedbackRepo` - Store user feedback
- `FavoritesRepo` - Manage favorites
- `PostsRepo` - Channel post records
- `MetricsRepo` - Post metrics snapshots
- `ABWinnersRepo` - A/B test winner management
- `EventsRepo` - Event logging

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BOT_TOKEN` | Yes | - | Telegram bot token from BotFather |
| `BOT_MODE` | No | `polling` | `polling` or `webhook` |
| `WEBHOOK_URL` | If webhook | - | Public URL for webhook |
| `WEBHOOK_PATH` | No | `/telegram/webhook` | Webhook endpoint path |
| `HOST` | No | `0.0.0.0` | Server bind address |
| `PORT` | No | `8000` | Server port |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./onepick.db` | Database connection URL |
| `ADMIN_TOKEN` | No | - | Admin authentication token |
| `LOG_LEVEL` | No | `INFO` | Logging level |

## Database Migrations

### Alembic Async Notes

The project uses async SQLAlchemy with aiosqlite. Alembic is configured for async in `alembic/env.py`:

- Uses `async_engine_from_config` for async engine creation
- Runs migrations via `asyncio.run()`
- `DATABASE_URL` must use `sqlite+aiosqlite://` prefix

### Common Commands

```bash
# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Rollback all migrations
alembic downgrade base

# Show current revision
alembic current

# Show migration history
alembic history

# Generate new migration (autogenerate)
alembic revision --autogenerate -m "Description"

# Generate empty migration
alembic revision -m "Description"
```

### Creating New Migrations

1. Modify models in `app/storage/models.py`
2. Generate migration:
   ```bash
   alembic revision --autogenerate -m "Add new_table"
   ```
3. Review generated migration in `alembic/versions/`
4. Apply:
   ```bash
   alembic upgrade head
   ```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test file
pytest app/tests/test_storage.py

# Run with verbose output
pytest -v
```

## Channel Posting

To post content to a channel, the bot must be added as an **administrator** with permission to post messages.

1. Add the bot to your channel as admin
2. Grant "Post Messages" permission
3. Use the channel's username or ID in your configuration

## Development

### Code Style

```bash
ruff check .
ruff format .
```

### Type Checking

```bash
pip install mypy
mypy app/
```

### Repository Pattern Usage

```python
from app.storage import get_session_factory, UsersRepo, ItemsRepo

async def example():
    factory = get_session_factory()

    async with factory() as session:
        # Create repos with injected session
        users = UsersRepo(session)
        items = ItemsRepo(session)

        # Use repos
        user = await users.get_or_create_user("12345")
        candidates = await items.list_candidates(item_type="movie", limit=10)
```

## License

Private - All rights reserved.
