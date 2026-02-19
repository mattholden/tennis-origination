"""
Event summaries pipeline: pull sport_event_ids from BQ -> fetch (parallel) -> transform -> upload.
Closed loop: run in isolation via Runner.run("event_summaries"). Depends on season_brackets table being populated.
"""

import asyncio

import core.raw_store

from injestion.sportradar.pipelines.concurrency import semaphore


async def run(client, manager, bq) -> None:
    """End-to-end: get sport event ids from BQ, fetch summaries in parallel, write to BigQuery."""
    sport_event_ids = bq.get_sport_event_ids_from_season_brackets_table(
        manager.get_table_id("season_brackets")
    )

    sport_event_ids = ["sr:sport_event:63100845"]
    event_summary_table_id = manager.get_table_id("event_summary")
    event_statistics_table_id = manager.get_table_id("event_statistics")
    event_timeline_table_id = manager.get_table_id("event_timeline")

    async def fetch_event_summary(sport_event_id: str) -> tuple[str, dict]:
        async with semaphore:
            raw = await manager.get_raw_async("event_summary", client, sport_event_id=sport_event_id)
            return (sport_event_id, raw)

    total = len(sport_event_ids)
    pending = {asyncio.create_task(fetch_event_summary(sid)) for sid in sport_event_ids}
    completed = 0
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            try:
                sport_event_id, raw = task.result()
            except Exception as e:
                print(f"Error fetching event summary: {e}")
                continue
            event_summary_rows = manager.raw_to_rows("event_summary", raw, sport_event_id=sport_event_id)
            event_statistics = manager.raw_to_rows("event_statistics", raw, sport_event_id=sport_event_id)
            event_timeline = manager.raw_to_rows("event_timeline", raw, sport_event_id=sport_event_id)
            bq.write_rows(event_summary_table_id, event_summary_rows)
            bq.write_rows(event_statistics_table_id, event_statistics)
            bq.write_rows(event_timeline_table_id, event_timeline)
            completed += 1
            msg = f"Fetched {completed}/{total} event summaries"
            print(f"\r{msg:<50}", end="", flush=True)
            core.raw_store.save_raw_to_json(raw, "event_summary_raw_63100845", source="sportradar")