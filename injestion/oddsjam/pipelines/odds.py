"""
OddsJam odds pipeline: pull fixture_ids from BQ fixtures table, fetch odds in parallel (async),
transform and batch-upload to BigQuery. Throttled to avoid OpticOdds 429 rate limits.

After all inserts, removes stale no-odds sentinel rows for fixtures that received
at least one real odds row in this run.
"""

import asyncio
import json
import random
from pathlib import Path

# Odds API rate limit: use fewer concurrent requests and a random delay between starts.
# Random delay (0.5–1s) reduces synchronized bursts; tune semaphore if you still see 429.
ODDS_MAX_CONCURRENT = 2
ODDS_DELAY_MIN_SEC = 0.8
ODDS_DELAY_MAX_SEC = 1.2

# Test run: set to an int to process only that many fixtures (e.g. 100). Set to None for full run.
ODDS_TEST_LIMIT = None

# Retry failed fetches (e.g. 429) up to this many times per fixture before skipping.
ODDS_MAX_RETRIES = 3

# Rows to accumulate before flushing to BigQuery (fewer, larger inserts).
ODDS_BATCH_SIZE = 2000

# Where to write fixture IDs that failed after all retries (relative to project root).
ODDS_FAILED_FIXTURE_IDS_JSON = "raw_data/oddsjam/odds_failed_fixture_ids.json"

# If set, load fixture IDs from this JSON file (list of strings) instead of the BQ fixtures table.
# Use to process only missing fixtures, e.g. "raw_data/oddsjam/odds_missing_fixture_ids.json"
ODDS_FIXTURE_IDS_JSON: str | None = "raw_data/oddsjam/odds_missing_fixture_ids.json"

_odds_semaphore = asyncio.Semaphore(ODDS_MAX_CONCURRENT)


async def run(client, manager, bq) -> None:
    """Get fixture ids from BQ (or from ODDS_FIXTURE_IDS_JSON if set), fetch odds in parallel (async), transform and batch-write to BQ."""
    fixtures_table_id = manager.get_table_id("oddsjam_fixtures")
    odds_table_id = manager.get_table_id("oddsjam_odds")
    if ODDS_FIXTURE_IDS_JSON:
        path = Path(ODDS_FIXTURE_IDS_JSON)
        if not path.is_file():
            raise FileNotFoundError(f"ODDS_FIXTURE_IDS_JSON not found: {path}")
        with open(path) as f:
            fixture_ids = json.load(f)
        if not isinstance(fixture_ids, list):
            raise TypeError(f"ODDS_FIXTURE_IDS_JSON must be a JSON list of fixture IDs, got {type(fixture_ids)}")
        print(f"Using {len(fixture_ids)} fixture IDs from {ODDS_FIXTURE_IDS_JSON}")
    else:
        fixture_ids = bq.get_fixture_ids_from_oddsjam_fixtures_table(fixtures_table_id)
    if ODDS_TEST_LIMIT is not None:
        fixture_ids = fixture_ids[:ODDS_TEST_LIMIT]
        print(f"Test run: limiting to {ODDS_TEST_LIMIT} fixtures")

    def flush(buffer: list) -> None:
        if not buffer:
            return
        n = len(buffer)
        try:
            merge_stats = bq.merge_odds_rows_by_odds_id(odds_table_id, buffer)
            print(
                (
                    f"\n  Processed {n} odds rows to {odds_table_id} "
                    f"(inserted={merge_stats['total_inserted_rows']}, "
                    f"inserted_keyed={merge_stats['inserted_keyed_rows']}, "
                    f"inserted_non_key={merge_stats['inserted_non_key_rows']}, "
                    f"inserted_non_key_fixture={merge_stats['inserted_non_key_rows_with_fixture_id']}, "
                    f"inserted_non_key_no_fixture={merge_stats['inserted_non_key_rows_without_fixture_id']}, "
                    f"deduped_source_keyed={merge_stats['source_keyed_rows_deduped']}, "
                    f"deduped_source_non_key_fixture={merge_stats['source_non_key_rows_with_fixture_id_deduped']})"
                ),
                flush=True,
            )
        except Exception as e:
            print(f"\nBigQuery write failed (table={odds_table_id}, rows={n}): {e}", flush=True)
            raise
        buffer.clear()

    total = len(fixture_ids)
    skipped_after_retries: list[str] = []
    batch: list = []
    fixtures_with_real_odds: set[str] = set()

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
                for _ in range(ODDS_MAX_CONCURRENT):
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
                async with _odds_semaphore:
                    delay = random.uniform(ODDS_DELAY_MIN_SEC, ODDS_DELAY_MAX_SEC)
                    await asyncio.sleep(delay)
                    try:
                        raw = await manager.get_raw_async("oddsjam_odds", client, fixture_id=fixture_id)
                        result_queue.put_nowait((fixture_id, raw))
                    except Exception:
                        print(f"\r  Fetch failed: {fixture_id}          ", flush=True)
                        if attempt + 1 < ODDS_MAX_RETRIES:
                            work_queue.put_nowait((fixture_id, attempt + 1))
                        else:
                            skipped_after_retries.append(fixture_id)
                            print(f"\n  Skipped after {ODDS_MAX_RETRIES} retries: {fixture_id}", flush=True)
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
            rows = manager.raw_to_rows("oddsjam_odds", raw, fixture_id=fixture_id)
            fixtures_with_real_odds.update(
                str(row["fixture_id"])
                for row in rows
                if row.get("odds_id") is not None and row.get("fixture_id") is not None
            )
            batch.extend(rows)
            if len(batch) >= ODDS_BATCH_SIZE:
                flush(batch)
            completed += 1
            print(f"\rOdds: {completed}/{total} fixtures", end="", flush=True)
        flush(batch)

    collector_task = asyncio.create_task(collector())
    worker_tasks = [asyncio.create_task(worker()) for _ in range(ODDS_MAX_CONCURRENT)]
    sentinel_task_handle = asyncio.create_task(sentinel_task())
    await asyncio.gather(sentinel_task_handle, *worker_tasks)
    result_queue.put_nowait(None)  # signal collector no more results
    await collector_task
    if fixtures_with_real_odds:
        deleted = bq.delete_stale_no_odds_rows_for_fixtures(
            odds_table_id,
            list(fixtures_with_real_odds),
        )
        print(
            f"  Cleanup removed {deleted} stale no-odds rows across {len(fixtures_with_real_odds)} fixtures",
            flush=True,
        )
    if skipped_after_retries:
        out_path = Path(ODDS_FAILED_FIXTURE_IDS_JSON)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(skipped_after_retries, f, indent=2)
        print(f"  Wrote {len(skipped_after_retries)} failed fixture IDs to {out_path}", flush=True)
    print()
