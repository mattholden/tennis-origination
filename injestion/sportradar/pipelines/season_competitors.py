"""
Season competitors pipeline: pull season_ids from BQ -> fetch (parallel) -> transform -> upload.
Closed loop: run in isolation via Runner.run("season_competitors"). Depends on seasons table being populated.
"""

import asyncio
import os

from injestion.sportradar.pipelines.concurrency import semaphore

DEFAULT_MIN_SEASON_START_DATE = "2026-01-01"


async def run(client, manager, bq) -> None:
    """End-to-end: get season ids from BQ, fetch competitors in parallel, write to BigQuery."""
    seasons_table_id = manager.get_table_id("seasons")
    min_season_start_date = os.environ.get(
        "SR_SEASON_MIN_START_DATE",
        DEFAULT_MIN_SEASON_START_DATE,
    )
    season_ids = bq.get_season_ids_from_seasons_table_by_min_start_date(
        seasons_table_id,
        min_start_date=min_season_start_date,
    )
    print(
        (
            "Season competitors source window: "
            f"start_date >= {min_season_start_date} ({len(season_ids)} seasons)"
        ),
        flush=True,
    )
    table_id = manager.get_table_id("season_competitors")

    async def fetch_one(season_id: str) -> tuple[str, dict]:
        async with semaphore:
            raw = await manager.get_raw_async("season_competitors", client, season_id=season_id)
            return (season_id, raw)

    total = len(season_ids)
    pending = {asyncio.create_task(fetch_one(sid)) for sid in season_ids}
    completed = 0
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            try:
                season_id, raw = task.result()
            except Exception as e:
                print(f"Error fetching season competitors: {e}")
                continue
            rows = manager.raw_to_rows("season_competitors", raw, season_id=season_id)
            merge_stats = bq.merge_season_competitor_rows_by_season_and_competitor(table_id, rows)
            if merge_stats["dropped_non_key_rows"] > 0:
                print(
                    (
                        "\n  Dropped season_competitors rows with missing keys: "
                        f"{merge_stats['dropped_non_key_rows']}"
                    ),
                    flush=True,
                )
            completed += 1
            msg = f"Fetched {completed}/{total} season competitors"
            print(f"\r{msg:<50}", end="", flush=True)
    print()