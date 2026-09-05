"""Demo Database Reset Utility.

Dev-only script (gated by APP_ENV=dev) that wipes existing database tables
and re-seeds the 5 curated presentation scenarios from demo_seed.py.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from reclaim.config import get_settings
from reclaim.db.models import Base
from reclaim.db.session import dispose_engine, get_engine, init_engine
from reclaim.synthetic_data.demo_seed import seed_curated_demo_dataset

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def reset_demo_database() -> None:
    """Wipe database and re-seed 5 curated demo scenarios."""
    settings = get_settings()

    if settings.APP_ENV != "dev":
        logger.error(
            f"reset_demo.py can ONLY be run in APP_ENV=dev (current APP_ENV={settings.APP_ENV}). Aborting for safety!"
        )
        sys.exit(1)

    logger.info("Wiping existing database tables for demo reset...")
    await init_engine()
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    await dispose_engine()
    logger.info("Database wiped. Re-seeding curated demo dataset...")

    count = await seed_curated_demo_dataset()
    logger.info(f"Demo reset complete! {count} curated scenarios ready for live presentation.")


def main():
    asyncio.run(reset_demo_database())


if __name__ == "__main__":
    main()
