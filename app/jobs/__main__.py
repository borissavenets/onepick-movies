"""Run the scheduler as a standalone process.

Usage::

    python -m app.jobs.scheduler

This is useful when the bot runs in polling mode and you want the
scheduler in a separate process.
"""

import asyncio
import signal
import sys

from app.config import config
from app.logging import get_logger, setup_logging
from app.jobs.scheduler import (
    get_scheduler,
    setup_all_jobs,
    shutdown_scheduler,
    start_scheduler,
)

setup_logging(config.log_level)
logger = get_logger(__name__)


def _handle_signal(signum, frame):
    logger.info(f"Received signal {signum}, shutting down scheduler")
    shutdown_scheduler()
    sys.exit(0)


async def _run() -> None:
    start_scheduler()
    setup_all_jobs()
    logger.info("Scheduler running standalone – press Ctrl+C to stop")

    # Keep the event loop alive
    try:
        while get_scheduler().running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        shutdown_scheduler()


def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
