"""
Event summaries pipeline: pull sport_event_ids from BQ -> fetch via bounded workers -> transform -> batch upload.
Closed loop: run in isolation via Runner.run("event_summaries"). Depends on season_brackets table being populated.
Writes to three tables (event_summary, event_statistics, event_timeline); each has its own buffer and flushes at 2000 rows.
"""

import asyncio

from injestion.sportradar.pipelines.concurrency import semaphore

# Number of concurrent fetch workers (bounded concurrency).
EVENT_SUMMARY_MAX_CONCURRENT = 8

# Rows to accumulate per table before flushing to BigQuery.
EVENT_SUMMARY_BATCH_SIZE = 2000


async def run(client, manager, bq) -> None:
    """End-to-end: get sport event ids from BQ (excluding already in event_summary), fetch via queue/workers, batch-write to three tables."""
    season_brackets_table_id = manager.get_table_id("season_brackets")
    event_summary_table_id = manager.get_table_id("event_summary")
    event_statistics_table_id = manager.get_table_id("event_statistics")
    event_timeline_table_id = manager.get_table_id("event_timeline")

    all_sport_event_ids = bq.get_sport_event_ids_from_season_brackets_table(season_brackets_table_id)
    existing_sport_event_ids = set(
        bq.get_existing_sport_event_ids_from_event_summary_table(event_summary_table_id)
    )
    sport_event_ids = [eid for eid in all_sport_event_ids if eid not in existing_sport_event_ids]

    def flush(table_id: str, buffer: list) -> None:
        if not buffer:
            return
        n = len(buffer)
        try:
            bq.write_rows(table_id, buffer)
            print(f"\n  Flushed {n} rows to {table_id}", flush=True)
        except Exception as e:
            print(f"\nBigQuery write failed (table={table_id}, rows={n}): {e}", flush=True)
            raise
        buffer.clear()

    summary_batch: list = []
    statistics_batch: list = []
    timeline_batch: list = []

    total = len(sport_event_ids)
    work_queue: asyncio.Queue[str | None] = asyncio.Queue()
    result_queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

    for eid in sport_event_ids:
        work_queue.put_nowait(eid)
    # Sentinels added when all workers are idle and queue is empty.
    workers_in_progress = 0

    async def sentinel_task() -> None:
        while True:
            await asyncio.sleep(0.5)
            if workers_in_progress == 0 and work_queue.empty():
                for _ in range(EVENT_SUMMARY_MAX_CONCURRENT):
                    work_queue.put_nowait(None)
                break

    async def worker() -> None:
        nonlocal workers_in_progress
        while True:
            sport_event_id = await work_queue.get()
            if sport_event_id is None:
                break
            workers_in_progress += 1
            try:
                try:
                    async with semaphore:
                        raw = await manager.get_raw_async(
                            "event_summary", client, sport_event_id=sport_event_id
                        )
                    result_queue.put_nowait((sport_event_id, raw))
                except Exception as e:
                    print(f"\r  Fetch failed: {sport_event_id} — {e}          ", flush=True)
            finally:
                workers_in_progress -= 1
            work_queue.task_done()

    completed = 0

    async def collector() -> None:
        nonlocal completed
        while True:
            item = await result_queue.get()
            if item is None:
                break
            sport_event_id, raw = item
            summary_rows = manager.raw_to_rows(
                "event_summary", raw, sport_event_id=sport_event_id
            )
            statistics_rows = manager.raw_to_rows(
                "event_statistics", raw, sport_event_id=sport_event_id
            )
            timeline_rows = manager.raw_to_rows(
                "event_timeline", raw, sport_event_id=sport_event_id
            )
            summary_batch.extend(summary_rows)
            statistics_batch.extend(statistics_rows)
            timeline_batch.extend(timeline_rows)
            if len(summary_batch) >= EVENT_SUMMARY_BATCH_SIZE:
                flush(event_summary_table_id, summary_batch)
            if len(statistics_batch) >= EVENT_SUMMARY_BATCH_SIZE:
                flush(event_statistics_table_id, statistics_batch)
            if len(timeline_batch) >= EVENT_SUMMARY_BATCH_SIZE:
                flush(event_timeline_table_id, timeline_batch)
            completed += 1
            print(f"\rEvent summaries: {completed}/{total} events", end="", flush=True)
        flush(event_summary_table_id, summary_batch)
        flush(event_statistics_table_id, statistics_batch)
        flush(event_timeline_table_id, timeline_batch)

    collector_task = asyncio.create_task(collector())
    worker_tasks = [
        asyncio.create_task(worker()) for _ in range(EVENT_SUMMARY_MAX_CONCURRENT)
    ]
    sentinel_task_handle = asyncio.create_task(sentinel_task())
    await asyncio.gather(sentinel_task_handle, *worker_tasks)
    result_queue.put_nowait(None)
    await collector_task
    print()
