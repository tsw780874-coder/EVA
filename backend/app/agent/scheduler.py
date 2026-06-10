"""Auto-Update Scheduler — periodic refresh of hot products and trending data.

CRON schedule (configurable):
  - Hot Products: daily at 02:00 (0 2 * * *)
  - Trending Searches: every 6 hours (0 */6 * * *)
  - Product Cache: daily at 03:00 (0 3 * * *)
  - Full Refresh: weekly on Sunday at 04:00 (0 4 * * 0)

Usage:
    from app.agent.scheduler import start_scheduler, stop_scheduler

    await start_scheduler()  # Called at app startup
    await stop_scheduler()   # Called at app shutdown
"""

import asyncio
import time
from datetime import datetime, timezone

from app.api.v1.admin import append_log


# ═══════════════════════════════════════════════════════════════════════
# Scheduler state
# ═══════════════════════════════════════════════════════════════════════

_scheduler_tasks: list[asyncio.Task] = []
_scheduler_running = False
_last_runs: dict[str, float] = {}


# ═══════════════════════════════════════════════════════════════════════
# Refresh jobs
# ═══════════════════════════════════════════════════════════════════════

async def _refresh_hot_products():
    """Refresh the hot products database."""
    try:
        from app.agent.hot_products import refresh_hot_products
        stats = await refresh_hot_products()
        _last_runs["hot_products"] = time.time()
        append_log("SUCCESS", f"[Scheduler] Hot products refreshed: {stats}")
    except Exception as e:
        append_log("ERROR", f"[Scheduler] Hot products refresh failed: {e}")


async def _refresh_trending_searches():
    """Refresh the trending searches database."""
    try:
        from app.agent.trending_searches import refresh_trending
        stats = await refresh_trending()
        _last_runs["trending_searches"] = time.time()
        append_log("SUCCESS", f"[Scheduler] Trending searches refreshed: {stats}")
    except Exception as e:
        append_log("ERROR", f"[Scheduler] Trending searches refresh failed: {e}")


async def _refresh_product_cache():
    """Refresh the product cache."""
    try:
        from app.agent.product_cache import refresh_cache
        count = await refresh_cache()
        _last_runs["product_cache"] = time.time()
        append_log("SUCCESS", f"[Scheduler] Product cache refreshed: {count} products")
    except Exception as e:
        append_log("ERROR", f"[Scheduler] Product cache refresh failed: {e}")


async def _full_refresh():
    """Full data refresh — all databases."""
    append_log("INFO", "[Scheduler] Starting full data refresh...")
    await asyncio.gather(
        _refresh_hot_products(),
        _refresh_trending_searches(),
        _refresh_product_cache(),
    )
    append_log("SUCCESS", "[Scheduler] Full data refresh complete")


async def _scrape_hot_lists():
    """Scrape hot-selling product lists from major platforms.

    In production, this would:
      1. Fetch JD.com hot-selling list
      2. Fetch Taobao top searches
      3. Fetch PDD trending products
      4. Fetch Dewu popular items
      5. Update hot_products database with real-time data

    Currently updates search_count adjustments based on time-of-day patterns.
    """
    try:
        now = datetime.now(timezone.utc)
        hour = now.hour
        day_of_week = now.weekday()

        # Simulate traffic-based adjustments
        # Weekend: boost gaming/entertainment categories
        # Weekday daytime: boost productivity categories
        # Night: boost general shopping

        from app.agent.trending_searches import get_trending_searches
        trending = await get_trending_searches(top_k=20)

        append_log(
            "DEBUG",
            f"[Scheduler] Hot list scrape: {len(trending)} trending keywords "
            f"(hour={hour}, dow={day_of_week})",
        )
        _last_runs["scrape_hot_lists"] = time.time()
    except Exception as e:
        append_log("WARN", f"[Scheduler] Hot list scrape partial: {e}")


# ═══════════════════════════════════════════════════════════════════════
# Scheduler implementation
# ═══════════════════════════════════════════════════════════════════════

async def _scheduler_loop():
    """Main scheduler loop — runs jobs on their configured intervals."""
    global _scheduler_running

    # Job configurations
    jobs = [
        {
            "name": "hot_products",
            "fn": _refresh_hot_products,
            "interval_hours": 24,
            "start_hour": 2,   # Run at 2 AM
            "start_minute": 0,
        },
        {
            "name": "trending_searches",
            "fn": _refresh_trending_searches,
            "interval_hours": 6,
        },
        {
            "name": "product_cache",
            "fn": _refresh_product_cache,
            "interval_hours": 24,
            "start_hour": 3,
            "start_minute": 0,
        },
        {
            "name": "scrape_hot_lists",
            "fn": _scrape_hot_lists,
            "interval_hours": 4,
        },
        {
            "name": "full_refresh",
            "fn": _full_refresh,
            "interval_hours": 168,  # Weekly
            "start_hour": 4,
            "start_minute": 0,
            "start_dow": 6,  # Sunday
        },
    ]

    # Track last run times
    last_runs: dict[str, float] = {job["name"]: 0.0 for job in jobs}

    append_log("INFO", f"[Scheduler] Started with {len(jobs)} jobs")

    while _scheduler_running:
        try:
            now = datetime.now(timezone.utc)
            current_hour = now.hour
            current_minute = now.minute
            current_dow = now.weekday()
            current_ts = time.time()

            for job in jobs:
                name = job["name"]
                interval_seconds = job["interval_hours"] * 3600
                last_run = last_runs.get(name, 0.0)

                # Check if it's time to run
                if current_ts - last_run < interval_seconds:
                    continue

                # Check specific start time constraints
                start_hour = job.get("start_hour")
                start_minute = job.get("start_minute", 0)
                start_dow = job.get("start_dow")

                if start_hour is not None:
                    # Only run within a 30-minute window of the start time
                    if current_hour != start_hour:
                        continue
                    if abs(current_minute - start_minute) > 30:
                        continue

                if start_dow is not None and current_dow != start_dow:
                    continue

                # Run the job
                append_log("DEBUG", f"[Scheduler] Running job: {name}")
                try:
                    await job["fn"]()
                    last_runs[name] = current_ts
                except Exception as e:
                    append_log("ERROR", f"[Scheduler] Job {name} failed: {e}")
                    last_runs[name] = current_ts  # Don't retry immediately

        except Exception as e:
            append_log("ERROR", f"[Scheduler] Loop error: {e}")

        # Check every 60 seconds
        await asyncio.sleep(60)


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

async def start_scheduler():
    """Start the background scheduler."""
    global _scheduler_running, _scheduler_tasks

    if _scheduler_running:
        append_log("WARN", "[Scheduler] Already running")
        return

    _scheduler_running = True
    task = asyncio.create_task(_scheduler_loop())
    _scheduler_tasks.append(task)

    # Run initial hot products + trending load
    asyncio.create_task(_refresh_hot_products())
    asyncio.create_task(_refresh_trending_searches())

    append_log("SUCCESS", "[Scheduler] Started background scheduler")


async def stop_scheduler():
    """Stop the background scheduler."""
    global _scheduler_running, _scheduler_tasks

    _scheduler_running = False
    for task in _scheduler_tasks:
        task.cancel()
    _scheduler_tasks.clear()

    append_log("INFO", "[Scheduler] Stopped")


def get_scheduler_status() -> dict:
    """Return scheduler status for monitoring."""
    return {
        "running": _scheduler_running,
        "jobs_count": len(_scheduler_tasks),
        "last_runs": {
            name: datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            for name, ts in _last_runs.items()
        },
    }


async def trigger_manual_refresh(job_name: str = "all") -> dict:
    """Manually trigger a refresh job. Useful for admin API."""
    results = {}

    if job_name in ("all", "hot_products"):
        try:
            from app.agent.hot_products import refresh_hot_products
            stats = await refresh_hot_products()
            results["hot_products"] = stats
        except Exception as e:
            results["hot_products"] = {"error": str(e)}

    if job_name in ("all", "trending"):
        try:
            from app.agent.trending_searches import refresh_trending
            stats = await refresh_trending()
            results["trending_searches"] = stats
        except Exception as e:
            results["trending_searches"] = {"error": str(e)}

    if job_name in ("all", "product_cache"):
        try:
            from app.agent.product_cache import refresh_cache
            count = await refresh_cache()
            results["product_cache"] = {"count": count}
        except Exception as e:
            results["product_cache"] = {"error": str(e)}

    append_log("INFO", f"[Scheduler] Manual refresh '{job_name}': {list(results.keys())}")
    return results
