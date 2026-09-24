"""
Season competitors pipeline: pull season_ids from BQ -> fetch (parallel) -> transform -> upload.
Closed loop: run in isolation via Runner.run("season_competitors"). Depends on seasons table being populated.
"""

import asyncio
import json
import os
from pathlib import Path

from injestion.sportradar.pipelines.concurrency import semaphore

DEFAULT_MIN_SEASON_START_DATE = "2026-01-01"
SEASON_COMPETITORS_MAX_RETRIES = 3
SEASON_COMPETITORS_RETRY_DELAY_SECONDS = 1.0
SEASON_COMPETITORS_IDS_JSON_ENV = "SR_SEASON_COMPETITORS_IDS_JSON"
SEASON_COMPETITORS_FAILED_SEASON_IDS_JSON = (
    "raw_data/sportradar/failed_processes/season_competitors_failed_season_ids.json"
)


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


async def run(client, manager, bq) -> None:
    """End-to-end: get season ids from BQ, fetch competitors in parallel, write to BigQuery."""
    seasons_table_id = manager.get_table_id("seasons")
    season_ids_override_json = os.environ.get(SEASON_COMPETITORS_IDS_JSON_ENV)
    if season_ids_override_json:
        path = Path(season_ids_override_json)
        if not path.is_file():
            raise FileNotFoundError(f"{SEASON_COMPETITORS_IDS_JSON_ENV} not found: {path}")
        with open(path) as f:
            season_ids = json.load(f)
        if not isinstance(season_ids, list):
            raise TypeError(
                f"{SEASON_COMPETITORS_IDS_JSON_ENV} must be a JSON list of season IDs, got {type(season_ids)}"
            )
        season_ids = [str(sid) for sid in season_ids if sid]
        season_ids = list(dict.fromkeys(season_ids))
        print(
            f"Using {len(season_ids)} season IDs from {SEASON_COMPETITORS_IDS_JSON_ENV}={path}",
            flush=True,
        )
    else:
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
    failed_season_ids: list[str] = []
    failed_season_ids_seen: set[str] = set()
    failed_ids_out_path = Path(SEASON_COMPETITORS_FAILED_SEASON_IDS_JSON)

    def persist_failed_season_ids() -> None:
        """Persist failed season IDs atomically so partial progress survives crashes."""
        failed_ids_out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = failed_ids_out_path.with_name(f"{failed_ids_out_path.name}.tmp")
        with open(tmp_path, "w") as f:
            json.dump(failed_season_ids, f, indent=2)
        tmp_path.replace(failed_ids_out_path)

    async def fetch_one(season_id: str) -> tuple[str, dict]:
        last_exception: Exception | None = None
        for attempt in range(1, SEASON_COMPETITORS_MAX_RETRIES + 1):
            try:
                async with semaphore:
                    raw = await manager.get_raw_async("season_competitors", client, season_id=season_id)
                return (season_id, raw)
            except Exception as exc:
                last_exception = exc
                print(
                    (
                        f"\n  Fetch failed: {season_id} "
                        f"(attempt {attempt}/{SEASON_COMPETITORS_MAX_RETRIES}) "
                        f"— {_describe_fetch_exception(exc)}"
                    ),
                    flush=True,
                )
                if attempt < SEASON_COMPETITORS_MAX_RETRIES:
                    await asyncio.sleep(SEASON_COMPETITORS_RETRY_DELAY_SECONDS * attempt)

        raise RuntimeError(
            f"Failed to fetch season competitors for {season_id} after {SEASON_COMPETITORS_MAX_RETRIES} attempts."
        ) from last_exception

    total = len(season_ids)
    persist_failed_season_ids()
    print(f"Checkpointing failed season IDs to {failed_ids_out_path}", flush=True)
    pending: dict[asyncio.Task[tuple[str, dict]], str] = {
        asyncio.create_task(fetch_one(sid)): sid for sid in season_ids
    }
    completed = 0
    while pending:
        done, _ = await asyncio.wait(set(pending.keys()), return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            season_id = pending.pop(task)
            try:
                season_id, raw = task.result()
            except Exception as e:
                if season_id not in failed_season_ids_seen:
                    failed_season_ids_seen.add(season_id)
                    failed_season_ids.append(season_id)
                    try:
                        persist_failed_season_ids()
                    except Exception as write_exc:
                        print(
                            f"\n  Failed to checkpoint failed season IDs: {write_exc}",
                            flush=True,
                        )
                print(
                    f"\nError fetching season competitors after retries for {season_id}: {e}",
                    flush=True,
                )
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
    try:
        persist_failed_season_ids()
    except Exception as write_exc:
        print(f"\n  Failed to write final failed season IDs checkpoint: {write_exc}", flush=True)
    if failed_season_ids:
        print(
            f"\n  Checkpointed {len(failed_season_ids)} failed season IDs to {failed_ids_out_path}",
            flush=True,
        )
    print()