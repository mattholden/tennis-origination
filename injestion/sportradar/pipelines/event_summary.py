"""
Event summaries pipeline: pull sport_event_ids from BQ -> fetch with retries
(parallel) -> transform -> replace rows in event cohorts across
summary/statistics/timeline tables.

Closed loop: run in isolation via Runner.run("event_summary"). Depends on
season_brackets table being populated.
"""

import asyncio
import json
import os
import time
from pathlib import Path

# Number of concurrent fetch workers (bounded by queue worker count).
EVENT_SUMMARY_DEFAULT_MAX_CONCURRENT = 8
EVENT_SUMMARY_MAX_RETRIES = 3
EVENT_SUMMARY_RETRY_DELAY_SECONDS = 1.0
EVENT_SUMMARY_IDS_JSON_ENV = "SR_EVENT_SUMMARY_IDS_JSON"
EVENT_SUMMARY_MAX_CONCURRENT_ENV = "SR_EVENT_SUMMARY_MAX_CONCURRENT"
EVENT_SUMMARY_PROGRESS_LOG_EVERY_ENV = "SR_EVENT_SUMMARY_PROGRESS_LOG_EVERY"
EVENT_SUMMARY_WRITE_BATCH_EVENTS_ENV = "SR_EVENT_SUMMARY_WRITE_BATCH_EVENTS"
EVENT_SUMMARY_DEFAULT_PROGRESS_LOG_EVERY = 100
EVENT_SUMMARY_DEFAULT_WRITE_BATCH_EVENTS = 50
EVENT_SUMMARY_FAILED_SPORT_EVENT_IDS_JSON = (
    "raw_data/sportradar/failed_processes/event_summary_failed_sport_event_ids.json"
)
EVENT_SUMMARY_TERMINAL_MATCH_STATUSES = ("ended", "retired", "walkover")


def _describe_fetch_exception(exc: Exception) -> str:
    """Return concise one-line exception details for logs."""
    parts = [type(exc).__name__]
    response = getattr(exc, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)
        if status_code is not None:
            parts.append(f"status={status_code}")
        body = None
        try:
            body = response.text
        except Exception:
            body = None
        if body:
            snippet = " ".join(str(body).split())
            parts.append(f"error={snippet[:120]}")
    else:
        message = " ".join(str(exc).split())
        if " for url " in message:
            message = message.split(" for url ", 1)[0]
        if message:
            parts.append(f"error={message[:120]}")
    return " | ".join(parts)


def _positive_int_env(name: str, default: int) -> int:
    """Parse positive integer env var; fallback to default on invalid values."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        print(f"Invalid {name}={raw!r}; using default {default}.", flush=True)
        return default
    if value <= 0:
        print(f"Invalid {name}={raw!r}; must be > 0. Using default {default}.", flush=True)
        return default
    return value


async def run(client, manager, bq) -> None:
    """End-to-end: get event ids, fetch with retries, transform, replace rows in three event tables."""
    season_brackets_table_id = manager.get_table_id("season_brackets")
    event_summary_table_id = manager.get_table_id("event_summary")
    event_statistics_table_id = manager.get_table_id("event_statistics")
    event_timeline_table_id = manager.get_table_id("event_timeline")

    sport_event_ids_override_json = os.environ.get(EVENT_SUMMARY_IDS_JSON_ENV)
    if sport_event_ids_override_json:
        path = Path(sport_event_ids_override_json)
        if not path.is_file():
            raise FileNotFoundError(f"{EVENT_SUMMARY_IDS_JSON_ENV} not found: {path}")
        with open(path) as f:
            sport_event_ids = json.load(f)
        if not isinstance(sport_event_ids, list):
            raise TypeError(
                f"{EVENT_SUMMARY_IDS_JSON_ENV} must be a JSON list of sport_event_ids, got {type(sport_event_ids)}"
            )
        sport_event_ids = [str(eid) for eid in sport_event_ids if eid]
        sport_event_ids = list(dict.fromkeys(sport_event_ids))
        print(
            f"Using {len(sport_event_ids)} sport_event_ids from {EVENT_SUMMARY_IDS_JSON_ENV}={path}",
            flush=True,
        )
    else:
        all_sport_event_ids = bq.get_sport_event_ids_from_season_brackets_table(season_brackets_table_id)
        sport_event_ids = bq.get_sport_event_ids_for_event_summary_processing(
            season_brackets_table_id,
            event_summary_table_id,
            terminal_match_statuses=EVENT_SUMMARY_TERMINAL_MATCH_STATUSES,
        )
        print(
            (
                "Event summary scope: "
                f"all={len(all_sport_event_ids)} "
                f"to_process={len(sport_event_ids)} "
                f"terminal_statuses={EVENT_SUMMARY_TERMINAL_MATCH_STATUSES}"
            ),
            flush=True,
        )

    failed_sport_event_ids: list[str] = []
    failed_sport_event_ids_seen: set[str] = set()
    failed_ids_out_path = Path(EVENT_SUMMARY_FAILED_SPORT_EVENT_IDS_JSON)
    max_concurrent = _positive_int_env(
        EVENT_SUMMARY_MAX_CONCURRENT_ENV,
        EVENT_SUMMARY_DEFAULT_MAX_CONCURRENT,
    )
    progress_log_every = _positive_int_env(
        EVENT_SUMMARY_PROGRESS_LOG_EVERY_ENV,
        EVENT_SUMMARY_DEFAULT_PROGRESS_LOG_EVERY,
    )
    write_batch_events = _positive_int_env(
        EVENT_SUMMARY_WRITE_BATCH_EVENTS_ENV,
        EVENT_SUMMARY_DEFAULT_WRITE_BATCH_EVENTS,
    )
    print(
        (
            "Event summary runtime config: "
            f"workers={max_concurrent} retries={EVENT_SUMMARY_MAX_RETRIES} "
            f"progress_log_every={progress_log_every} "
            f"write_batch_events={write_batch_events}"
        ),
        flush=True,
    )

    def persist_failed_sport_event_ids() -> None:
        """Persist failed sport_event_ids atomically so partial progress survives crashes."""
        failed_ids_out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = failed_ids_out_path.with_name(f"{failed_ids_out_path.name}.tmp")
        with open(tmp_path, "w") as f:
            json.dump(failed_sport_event_ids, f, indent=2)
        tmp_path.replace(failed_ids_out_path)

    async def fetch_one(sport_event_id: str) -> tuple[str, dict]:
        last_exception: Exception | None = None
        for attempt in range(1, EVENT_SUMMARY_MAX_RETRIES + 1):
            try:
                raw = await manager.get_raw_async(
                    "event_summary",
                    client,
                    sport_event_id=sport_event_id,
                )
                return (sport_event_id, raw)
            except Exception as exc:
                last_exception = exc
                metrics["fetch_attempt_failures"] += 1
                exc_type = type(exc).__name__
                if exc_type == "ConnectTimeout":
                    metrics["connect_timeout_attempt_failures"] += 1
                elif exc_type == "ConnectError":
                    metrics["connect_error_attempt_failures"] += 1
                print(
                    (
                        f"\n  Fetch failed: {sport_event_id} "
                        f"(attempt {attempt}/{EVENT_SUMMARY_MAX_RETRIES}) "
                        f"— {_describe_fetch_exception(exc)}"
                    ),
                    flush=True,
                )
                if attempt < EVENT_SUMMARY_MAX_RETRIES:
                    await asyncio.sleep(EVENT_SUMMARY_RETRY_DELAY_SECONDS * attempt)

        raise RuntimeError(
            f"Failed to fetch event summary for {sport_event_id} after {EVENT_SUMMARY_MAX_RETRIES} attempts."
        ) from last_exception

    total = len(sport_event_ids)
    persist_failed_sport_event_ids()
    print(f"Checkpointing failed sport_event_ids to {failed_ids_out_path}", flush=True)

    started_at = time.monotonic()
    metrics: dict[str, int] = {
        "fetch_attempt_failures": 0,
        "connect_timeout_attempt_failures": 0,
        "connect_error_attempt_failures": 0,
        "batch_write_failures": 0,
    }
    completed = 0
    work_queue: asyncio.Queue[str | None] = asyncio.Queue()
    result_queue: asyncio.Queue[
        tuple[str, list[dict], list[dict], list[dict]] | None
    ] = asyncio.Queue(maxsize=max(write_batch_events * 2, max_concurrent * 4))
    for sport_event_id in sport_event_ids:
        work_queue.put_nowait(sport_event_id)
    for _ in range(max_concurrent):
        work_queue.put_nowait(None)

    def mark_failed(sport_event_id: str) -> None:
        """Record a failed event once and checkpoint immediately."""
        if sport_event_id in failed_sport_event_ids_seen:
            return
        failed_sport_event_ids_seen.add(sport_event_id)
        failed_sport_event_ids.append(sport_event_id)
        try:
            persist_failed_sport_event_ids()
        except Exception as write_exc:
            print(
                f"\n  Failed to checkpoint failed sport_event_ids: {write_exc}",
                flush=True,
            )

    def log_metrics_if_due() -> None:
        if completed == 0:
            return
        if completed % progress_log_every != 0 and completed != total:
            return
        elapsed_seconds = max(time.monotonic() - started_at, 1e-9)
        events_per_minute = completed / elapsed_seconds * 60.0
        timeout_per_100_events = (
            metrics["connect_timeout_attempt_failures"] / completed * 100.0
        )
        print(
            (
                "\n  Metrics: "
                f"rate={events_per_minute:.2f} events/min | "
                f"connect_timeouts={metrics['connect_timeout_attempt_failures']} "
                f"({timeout_per_100_events:.2f}/100 events) | "
                f"connect_errors={metrics['connect_error_attempt_failures']} | "
                f"fetch_attempt_failures={metrics['fetch_attempt_failures']} | "
                f"batch_write_failures={metrics['batch_write_failures']}"
            ),
            flush=True,
        )

    async def worker() -> None:
        while True:
            sport_event_id = await work_queue.get()
            try:
                if sport_event_id is None:
                    await result_queue.put(None)
                    return

                try:
                    sport_event_id, raw = await fetch_one(sport_event_id)
                except Exception as fetch_exc:
                    mark_failed(sport_event_id)
                    print(
                        f"\nError fetching event summary after retries for {sport_event_id}: {fetch_exc}",
                        flush=True,
                    )
                    continue

                try:
                    summary_rows = manager.raw_to_rows(
                        "event_summary",
                        raw,
                        sport_event_id=sport_event_id,
                    )
                    statistics_rows = manager.raw_to_rows(
                        "event_statistics",
                        raw,
                        sport_event_id=sport_event_id,
                    )
                    timeline_rows = manager.raw_to_rows(
                        "event_timeline",
                        raw,
                        sport_event_id=sport_event_id,
                    )
                except Exception as process_exc:
                    mark_failed(sport_event_id)
                    print(
                        f"\nError processing event summary rows for {sport_event_id}: {process_exc}",
                        flush=True,
                    )
                    continue

                await result_queue.put(
                    (
                        sport_event_id,
                        summary_rows,
                        statistics_rows,
                        timeline_rows,
                    )
                )
            finally:
                work_queue.task_done()

    async def writer() -> None:
        nonlocal completed
        finished_workers = 0
        batch_event_ids: list[str] = []
        batch_summary_rows: list[dict] = []
        batch_statistics_rows: list[dict] = []
        batch_timeline_rows: list[dict] = []

        async def flush_batch() -> None:
            nonlocal completed
            if not batch_event_ids:
                return

            cohort_event_ids = list(dict.fromkeys(batch_event_ids))
            try:
                bq.replace_event_summary_rows_for_events(
                    event_summary_table_id,
                    cohort_event_ids,
                    batch_summary_rows,
                )
                bq.replace_event_statistics_rows_for_events(
                    event_statistics_table_id,
                    cohort_event_ids,
                    batch_statistics_rows,
                )
                bq.replace_event_timeline_rows_for_events(
                    event_timeline_table_id,
                    cohort_event_ids,
                    batch_timeline_rows,
                )
                completed += len(cohort_event_ids)
                print(f"\rEvent summaries: {completed}/{total} events", end="", flush=True)
                log_metrics_if_due()
            except Exception as batch_exc:
                metrics["batch_write_failures"] += 1
                for sport_event_id in cohort_event_ids:
                    mark_failed(sport_event_id)
                print(
                    (
                        "\nBatch write failed for event_summary cohort "
                        f"(size={len(cohort_event_ids)}): {batch_exc}"
                    ),
                    flush=True,
                )
            finally:
                batch_event_ids.clear()
                batch_summary_rows.clear()
                batch_statistics_rows.clear()
                batch_timeline_rows.clear()

        while finished_workers < max_concurrent:
            item = await result_queue.get()
            try:
                if item is None:
                    finished_workers += 1
                    continue

                (
                    sport_event_id,
                    summary_rows,
                    statistics_rows,
                    timeline_rows,
                ) = item
                batch_event_ids.append(sport_event_id)
                batch_summary_rows.extend(summary_rows)
                batch_statistics_rows.extend(statistics_rows)
                batch_timeline_rows.extend(timeline_rows)

                if len(batch_event_ids) >= write_batch_events:
                    await flush_batch()
            finally:
                result_queue.task_done()

        await flush_batch()

    workers = [asyncio.create_task(worker()) for _ in range(max_concurrent)]
    writer_task = asyncio.create_task(writer())
    await work_queue.join()
    await asyncio.gather(*workers)
    await result_queue.join()
    await writer_task

    try:
        persist_failed_sport_event_ids()
    except Exception as write_exc:
        print(f"\n  Failed to write final failed sport_event_ids checkpoint: {write_exc}", flush=True)
    if failed_sport_event_ids:
        print(
            (
                f"\n  Checkpointed {len(failed_sport_event_ids)} failed sport_event_ids "
                f"to {failed_ids_out_path}"
            ),
            flush=True,
        )
    total_elapsed_seconds = max(time.monotonic() - started_at, 1e-9)
    overall_events_per_minute = completed / total_elapsed_seconds * 60.0
    timeout_per_100_events = (
        metrics["connect_timeout_attempt_failures"] / completed * 100.0
        if completed
        else 0.0
    )
    print(
        (
            "Event summary final metrics: "
            f"completed={completed}/{total} "
            f"rate={overall_events_per_minute:.2f} events/min "
            f"connect_timeouts={metrics['connect_timeout_attempt_failures']} "
            f"({timeout_per_100_events:.2f}/100 events) "
            f"connect_errors={metrics['connect_error_attempt_failures']} "
            f"fetch_attempt_failures={metrics['fetch_attempt_failures']} "
            f"batch_write_failures={metrics['batch_write_failures']}"
        ),
        flush=True,
    )
    print()
