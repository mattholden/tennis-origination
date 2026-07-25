"""
OddsJam odds pipeline: pull fixture_ids from BQ fixtures table, fetch odds in
parallel (async), transform and batch-upload to BigQuery.

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
# Use to process a targeted fixture-id list, e.g. missing or failed fixtures.
ODDS_FIXTURE_IDS_JSON: str | None = None

# By default, run incrementally and fetch odds only for fixtures missing odds rows.
ODDS_ONLY_MISSING_FIXTURES = True

_odds_semaphore = asyncio.Semaphore(ODDS_MAX_CONCURRENT)


def _describe_fetch_exception(exc: Exception) -> str:
    """Return concise one-line exception details for terminal prints."""
    parts = [type(exc).__name__]
    response = getattr(exc, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)
        if status_code is not None:
            parts.append(f"status={status_code}")
        error_message = None
        try:
            payload = response.json()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            for key in ("error", "message", "detail"):
                value = payload.get(key)
                if value:
                    error_message = value
                    break
        try:
            body = response.text
        except Exception:
            body = None
        snippet_source = error_message if error_message is not None else body
        if snippet_source:
            snippet = " ".join(str(snippet_source).split())
            parts.append(f"error={snippet[:120]}")
    else:
        message = " ".join(str(exc).split())
        if " for url " in message:
            message = message.split(" for url ", 1)[0]
        if message:
            parts.append(f"error={message[:120]}")
    return " | ".join(parts)


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
    elif ODDS_ONLY_MISSING_FIXTURES:
        fixture_ids = bq.get_fixture_ids_missing_odds_rows(fixtures_table_id, odds_table_id)
        print(
            (
                "Incremental odds mode: using fixture IDs missing from odds table "
                f"({len(fixture_ids)} fixtures)"
            ),
            flush=True,
        )
    else:
        fixture_ids = bq.get_fixture_ids_from_oddsjam_fixtures_table(fixtures_table_id)
        print(
            f"Full odds mode: using all fixture IDs from fixtures table ({len(fixture_ids)} fixtures)",
            flush=True,
        )
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
    skipped_after_retries_seen: set[str] = set()
    failed_ids_out_path = Path(ODDS_FAILED_FIXTURE_IDS_JSON)

    def persist_failed_fixture_ids() -> None:
        """Persist failed fixture ids atomically so partial progress survives crashes."""
        failed_ids_out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = failed_ids_out_path.with_name(f"{failed_ids_out_path.name}.tmp")
        with open(tmp_path, "w") as f:
            json.dump(skipped_after_retries, f, indent=2)
        tmp_path.replace(failed_ids_out_path)

    # Reset checkpoint file at run start so it tracks this run's failures.
    persist_failed_fixture_ids()
    print(f"Checkpointing failed fixture IDs to {failed_ids_out_path}", flush=True)
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
                    except Exception as e:
                        print(
                            f"\r  Fetch failed: {fixture_id} — {_describe_fetch_exception(e)}",
                            flush=True,
                        )
                        if attempt + 1 < ODDS_MAX_RETRIES:
                            work_queue.put_nowait((fixture_id, attempt + 1))
                        else:
                            if fixture_id not in skipped_after_retries_seen:
                                skipped_after_retries_seen.add(fixture_id)
                                skipped_after_retries.append(fixture_id)
                                try:
                                    persist_failed_fixture_ids()
                                except Exception as write_exc:
                                    print(
                                        f"\n  Failed to checkpoint failed fixture IDs: {write_exc}",
                                        flush=True,
                                    )
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
    worker_bundle_task = asyncio.gather(sentinel_task_handle, *worker_tasks)

    try:
        # Wait for whichever side completes first so we can react immediately.
        # Using FIRST_EXCEPTION can deadlock here when workers finish cleanly,
        # because the collector cannot finish until it receives its sentinel.
        done, _ = await asyncio.wait(
            {collector_task, worker_bundle_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if collector_task in done:
            collector_exc = collector_task.exception()
            if collector_exc is not None:
                worker_bundle_task.cancel()
                await asyncio.gather(worker_bundle_task, return_exceptions=True)
                raise RuntimeError(
                    "Collector task failed; cancelled workers and stopping odds pipeline."
                ) from collector_exc

            # Collector should normally finish only after we send a sentinel; if it
            # exits early without error, still await workers and surface failures.
            await worker_bundle_task
            worker_exc = worker_bundle_task.exception()
            if worker_exc is not None:
                raise RuntimeError(
                    "Worker/sentinel task failed after collector completed."
                ) from worker_exc
        else:
            worker_exc = worker_bundle_task.exception()
            if worker_exc is not None:
                collector_task.cancel()
                await asyncio.gather(collector_task, return_exceptions=True)
                raise RuntimeError(
                    "Worker/sentinel task failed; cancelled collector and stopping odds pipeline."
                ) from worker_exc

            if not collector_task.done():
                result_queue.put_nowait(None)  # signal collector no more results
                await collector_task
    finally:
        if not worker_bundle_task.done():
            worker_bundle_task.cancel()
            await asyncio.gather(worker_bundle_task, return_exceptions=True)
        if not collector_task.done():
            collector_task.cancel()
            await asyncio.gather(collector_task, return_exceptions=True)
    if fixtures_with_real_odds:
        deleted = bq.delete_stale_no_odds_rows_for_fixtures(
            odds_table_id,
            list(fixtures_with_real_odds),
        )
        print(
            f"  Cleanup removed {deleted} stale no-odds rows across {len(fixtures_with_real_odds)} fixtures",
            flush=True,
        )
    try:
        persist_failed_fixture_ids()
    except Exception as write_exc:
        print(f"  Failed to write final failed fixture IDs checkpoint: {write_exc}", flush=True)
    if skipped_after_retries:
        print(
            f"  Checkpointed {len(skipped_after_retries)} failed fixture IDs to {failed_ids_out_path}",
            flush=True,
        )
    print()
