"""
Season competitors pipeline: pull season_ids from BQ -> fetch (parallel) -> transform -> upload.
Closed loop: run in isolation via Runner.run("season_competitors"). Depends on seasons table being populated.
"""

import asyncio

from injestion.sportradar.pipelines.concurrency import semaphore


async def run(client, manager, bq) -> None:
    """End-to-end: get season ids from BQ, fetch competitors in parallel, write to BigQuery."""
    season_ids = bq.get_season_ids_for_major_competitions(
        manager.get_table_id("seasons")
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
            bq.write_rows(table_id, rows)
            completed += 1
            msg = f"Fetched {completed}/{total} season competitors"
            print(f"\r{msg:<50}", end="", flush=True)
    print()