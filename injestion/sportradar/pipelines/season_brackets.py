"""
Season brackets pipeline: pull season_ids from BQ -> fetch via bounded workers -> transform -> batch upload.
Closed loop: run in isolation via Runner.run("season_brackets"). Depends on seasons table being populated.
Uses a work queue + fixed workers and a collector that batches rows to BigQuery (2000 rows per flush).
"""

import asyncio

from injestion.sportradar.pipelines.concurrency import semaphore

# Number of concurrent fetch workers (bounded concurrency; semaphore also limits in-flight requests).
BRACKETS_MAX_CONCURRENT = 8

# Rows to accumulate before flushing to BigQuery.
BRACKETS_BATCH_SIZE = 2000


async def run(client, manager, bq) -> None:
    """End-to-end: get season ids from BQ (excluding already in season_brackets), fetch via queue/workers, batch-write to BigQuery."""
    season_brackets_table_id = manager.get_table_id("season_brackets")
    seasons_table_id = manager.get_table_id("seasons")
    all_season_ids = bq.get_seasons_from_seasons_table(seasons_table_id)
    existing_season_ids = set(
        bq.get_existing_season_ids_from_season_brackets_table(season_brackets_table_id)
    )
    season_ids = [sid for sid in all_season_ids if sid not in existing_season_ids]

    def flush(buffer: list) -> None:
        if not buffer:
            return
        n = len(buffer)
        try:
            bq.write_rows(season_brackets_table_id, buffer)
            print(f"\n  Flushed {n} rows to {season_brackets_table_id}", flush=True)
        except Exception as e:
            print(f"\nBigQuery write failed (table={season_brackets_table_id}, rows={n}): {e}", flush=True)
            raise
        buffer.clear()

    total = len(season_ids)
    batch: list = []
    work_queue: asyncio.Queue[str | None] = asyncio.Queue()
    result_queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

    for sid in season_ids:
        work_queue.put_nowait(sid)
    # Sentinels added when all workers are idle and queue is empty.
    workers_in_progress = 0

    async def sentinel_task() -> None:
        while True:
            await asyncio.sleep(0.5)
            if workers_in_progress == 0 and work_queue.empty():
                for _ in range(BRACKETS_MAX_CONCURRENT):
                    work_queue.put_nowait(None)
                break

    async def worker() -> None:
        nonlocal workers_in_progress
        while True:
            season_id = await work_queue.get()
            if season_id is None:
                break
            workers_in_progress += 1
            try:
                try:
                    async with semaphore:
                        raw = await manager.get_raw_async("season_brackets", client, season_id=season_id)
                    result_queue.put_nowait((season_id, raw))
                except Exception as e:
                    print(f"\r  Fetch failed: {season_id} — {e}          ", flush=True)
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
            season_id, raw = item
            rows = manager.raw_to_rows("season_brackets", raw, season_id=season_id)
            batch.extend(rows)
            if len(batch) >= BRACKETS_BATCH_SIZE:
                flush(batch)
            completed += 1
            print(f"\rSeason brackets: {completed}/{total} seasons", end="", flush=True)
        flush(batch)

    collector_task = asyncio.create_task(collector())
    worker_tasks = [asyncio.create_task(worker()) for _ in range(BRACKETS_MAX_CONCURRENT)]
    sentinel_task_handle = asyncio.create_task(sentinel_task())
    await asyncio.gather(sentinel_task_handle, *worker_tasks)
    result_queue.put_nowait(None)
    await collector_task
    print()
