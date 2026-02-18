"""
Season brackets pipeline: pull season_ids from BQ -> fetch (parallel) -> transform -> upload.
Closed loop: run in isolation via Runner.run("season_brackets"). Depends on seasons table being populated.
"""

import asyncio

import core.raw_store

from injestion.sportradar.pipelines.concurrency import semaphore


async def run(client, manager, bq) -> None:
    """End-to-end: get season ids from BQ, fetch brackets in parallel, write to BigQuery."""
    season_ids = bq.get_season_ids_for_major_competitions(
        manager.get_table_id("seasons")
    )
    table_id = manager.get_table_id("season_brackets")

    async def fetch_season_bracket(season_id: str) -> tuple[str, dict]:
        async with semaphore:
            raw = await manager.get_raw_async("season_brackets", client, season_id=season_id)
            return (season_id, raw)

    total = len(season_ids)
    pending = {asyncio.create_task(fetch_season_bracket(sid)) for sid in season_ids}
    completed = 0
    #season_brackets = {}
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            try:
                season_id, raw = task.result()
            except Exception as e:
                print(f"Error fetching season bracket: {e}")
                continue
            #season_brackets[season_id] = raw
            rows = manager.raw_to_rows("season_brackets", raw, season_id=season_id)
            bq.write_rows(table_id, rows)
            completed += 1
            msg = f"Fetched {completed}/{total} season brackets"
            print(f"\r{msg:<50}", end="", flush=True)

    print()
    #core.raw_store.save_raw_to_json(season_brackets, "season_brackets", source="sportradar")