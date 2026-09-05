"""Clean-Clone Smoke Test Script.

Validates application health, runs database migrations/check, executes full
44-case pytest suite, and verifies API endpoints (/health, /dashboard/scoreboard, /dashboard/queue).
Exits 0 ONLY if all checks succeed.
"""

import sys
import subprocess
import logging
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("smoke_test")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_cmd(cmd: list[str], description: str) -> None:
    """Run a sub-command and exit 1 if it fails."""
    logger.info(f"Running: {description} ('{' '.join(cmd)}')")
    res = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if res.returncode != 0:
        logger.error(f"FAILED: {description} exited with code {res.returncode}")
        sys.exit(1)
    logger.info(f"PASSED: {description}")


def test_api_endpoints() -> None:
    """Test API endpoints in-process via httpx AsyncClient."""
    logger.info("Testing API endpoints (/health, /dashboard/scoreboard, /dashboard/queue)...")
    import asyncio
    from httpx import ASGITransport, AsyncClient
    from reclaim.main import app

    async def _test():
        from reclaim.db.models import Base
        from reclaim.db.session import get_engine

        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Health check
            h_resp = await client.get("/health")
            assert h_resp.status_code == 200, f"/health returned {h_resp.status_code}"
            assert h_resp.json().get("status") == "ok"
            logger.info("  ✓ /health endpoint OK")

            # 2. Scoreboard check
            s_resp = await client.get("/dashboard/scoreboard")
            assert s_resp.status_code == 200, f"/dashboard/scoreboard returned {s_resp.status_code}"
            sb = s_resp.json()
            assert "policies" in sb and "RECLAIM" in sb["policies"]
            logger.info("  ✓ /dashboard/scoreboard endpoint OK")

            # 3. Queue check
            q_resp = await client.get("/dashboard/queue")
            assert q_resp.status_code == 200, f"/dashboard/queue returned {q_resp.status_code}"
            assert "items" in q_resp.json()
            logger.info("  ✓ /dashboard/queue endpoint OK")

    asyncio.run(_test())
    logger.info("PASSED: API endpoint verification")


def main():
    logger.info("Starting RECLAIM Smoke Test Suite...")

    python_bin = sys.executable

    # Remove stale un-versioned local SQLite DB if running locally on SQLite
    sqlite_db_path = PROJECT_ROOT / "reclaim.db"
    if sqlite_db_path.exists():
        try:
            sqlite_db_path.unlink()
            logger.info("Cleaned stale local reclaim.db for clean migration test.")
        except Exception as e:
            logger.warning(f"Could not delete local reclaim.db: {e}")

    # 1. Run Alembic Upgrade / Migration check
    run_cmd([python_bin, "-m", "alembic", "upgrade", "head"], "Alembic Database Migration")

    # 2. Run Pytest suite
    run_cmd([python_bin, "-m", "pytest", "tests"], "Pytest Test Suite (92 tests)")

    # 3. Verify API Endpoints
    test_api_endpoints()

    logger.info("==========================================================")
    logger.info("ALL SMOKE TEST CHECKS PASSED SUCCESSFULLY! (Exit Code 0)")
    logger.info("==========================================================")
    sys.exit(0)


if __name__ == "__main__":
    main()
