"""
OddsJam results pipeline: pull fixture_ids from odds table, fetch results in
parallel (async), transform and batch-upload to BigQuery.
"""

import asyncio
import json
import random
from pathlib import Path

# Results API rate limit tuning.
RESULTS_MAX_CONCURRENT = 2
RESULTS_DELAY_MIN_SEC = 0.8
RESULTS_DELAY_MAX_SEC = 1.2

# Test run: set to an int to process only that many fixtures (e.g. 100). Set to None for full run.
RESULTS_TEST_LIMIT = None

# Retry failed fetches up to this many times per fixture before skipping.
RESULTS_MAX_RETRIES = 3

# Rows to accumulate before flushing to BigQuery.
RESULTS_BATCH_SIZE = 2000

# Where to write fixture IDs that failed after all retries (relative to project root).
RESULTS_FAILED_FIXTURE_IDS_JSON = "raw_data/oddsjam/results_failed_fixture_ids.json"

# Optional override: load fixture IDs from JSON list instead of odds table.
# Use to process only missing fixtures, e.g. "raw_data/oddsjam/results_missing_fixture_ids.json"
RESULTS_FIXTURE_IDS_JSON: str | None = None

_results_semaphore = asyncio.Semaphore(RESULTS_MAX_CONCURRENT)


async def run(client, manager, bq) -> None:
    """
    Get fixture ids from oddsjam_odds (or RESULTS_FIXTURE_IDS_JSON if set),
    fetch results in parallel (async), transform and batch-write to BQ.
    """
    odds_table_id = manager.get_table_id("oddsjam_odds")
    results_table_id = manager.get_table_id("oddsjam_results")
    if RESULTS_FIXTURE_IDS_JSON:
        path = Path(RESULTS_FIXTURE_IDS_JSON)
        if not path.is_file():
            raise FileNotFoundError(f"RESULTS_FIXTURE_IDS_JSON not found: {path}")
        with open(path) as f:
            fixture_ids = json.load(f)
        if not isinstance(fixture_ids, list):
            raise TypeError(
                f"RESULTS_FIXTURE_IDS_JSON must be a JSON list of fixture IDs, got {type(fixture_ids)}"
            )
        print(f"Using {len(fixture_ids)} fixture IDs from {RESULTS_FIXTURE_IDS_JSON}")
    else:
        fixture_ids = bq.get_fixture_ids_missing_results_rows(odds_table_id, results_table_id)
        print(
            (
                "Incremental results mode: using fixture IDs missing from results table "
                f"({len(fixture_ids)} fixtures)"
            ),
            flush=True,
        )

    fixture_ids = [str(fid) for fid in fixture_ids if fid]
    fixture_ids = list(dict.fromkeys(fixture_ids))

    if RESULTS_TEST_LIMIT is not None:
        fixture_ids = fixture_ids[:RESULTS_TEST_LIMIT]
        print(f"Test run: limiting to {RESULTS_TEST_LIMIT} fixtures")

    def flush(buffer: list) -> None:
        if not buffer:
            return
        n = len(buffer)
        try:
            bq.write_rows(results_table_id, buffer)
            print(f"\n  Flushed {n} rows to {results_table_id}", flush=True)
        except Exception as e:
            print(f"\nBigQuery write failed (table={results_table_id}, rows={n}): {e}", flush=True)
            raise
        buffer.clear()

    total = len(fixture_ids)
    skipped_after_retries: list[str] = []
    batch: list = []

    work_queue: asyncio.Queue[tuple[str, int] | None] = asyncio.Queue()
    result_queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()
    for fid in fixture_ids:
        work_queue.put_nowait((fid, 0))
    # Sentinels added when all workers are idle and queue is empty (so no retry can be added after Nones).
    workers_in_progress = 0

    async def sentinel_task() -> None:
        while True:
            await asyncio.sleep(0.5)
            if workers_in_progress == 0 and work_queue.empty():
                for _ in range(RESULTS_MAX_CONCURRENT):
                    work_queue.put_nowait(None)
                break

    async def worker() -> None:
        nonlocal workers_in_progress
        while True:
            item = await work_queue.get()
            if item is None:
                break
            workers_in_progress += 1
            try:
                fixture_id, attempt = item
                async with _results_semaphore:
                    delay = random.uniform(RESULTS_DELAY_MIN_SEC, RESULTS_DELAY_MAX_SEC)
                    await asyncio.sleep(delay)
                    try:
                        raw = await manager.get_raw_async("oddsjam_results", client, fixture_id=fixture_id)
                        result_queue.put_nowait((fixture_id, raw))
                    except Exception:
                        print(f"\r  Fetch failed: {fixture_id}          ", flush=True)
                        if attempt + 1 < RESULTS_MAX_RETRIES:
                            work_queue.put_nowait((fixture_id, attempt + 1))
                        else:
                            skipped_after_retries.append(fixture_id)
                            print(
                                f"\n  Skipped after {RESULTS_MAX_RETRIES} retries: {fixture_id}",
                                flush=True,
                            )
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
            fixture_id, raw = item
            rows = manager.raw_to_rows("oddsjam_results", raw, fixture_id=fixture_id)
            batch.extend(rows)
            if len(batch) >= RESULTS_BATCH_SIZE:
                flush(batch)
            completed += 1
            print(f"\rResults: {completed}/{total} fixtures", end="", flush=True)
        flush(batch)

    collector_task = asyncio.create_task(collector())
    worker_tasks = [asyncio.create_task(worker()) for _ in range(RESULTS_MAX_CONCURRENT)]
    sentinel_task_handle = asyncio.create_task(sentinel_task())
    await asyncio.gather(sentinel_task_handle, *worker_tasks)
    result_queue.put_nowait(None)  # signal collector no more results
    await collector_task
    if skipped_after_retries:
        out_path = Path(RESULTS_FAILED_FIXTURE_IDS_JSON)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(skipped_after_retries, f, indent=2)
        print(f"  Wrote {len(skipped_after_retries)} failed fixture IDs to {out_path}", flush=True)
    print()
