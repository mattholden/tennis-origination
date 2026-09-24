"""
Season brackets pipeline: pull season_ids from BQ -> fetch with retries (parallel)
-> transform -> replace rows for each fetched season.

Closed loop: run in isolation via Runner.run("season_brackets"). Depends on
seasons table being populated.
"""

import asyncio
import json
import os
from pathlib import Path

from injestion.sportradar.pipelines.concurrency import semaphore

# Number of concurrent fetch workers (bounded concurrency; semaphore also limits in-flight requests).
BRACKETS_MAX_CONCURRENT = 8
SEASON_BRACKETS_MAX_RETRIES = 3
SEASON_BRACKETS_RETRY_DELAY_SECONDS = 1.0
SEASON_BRACKETS_IDS_JSON_ENV = "SR_SEASON_BRACKETS_IDS_JSON"
SEASON_BRACKETS_FAILED_SEASON_IDS_JSON = (
    "raw_data/sportradar/failed_processes/season_brackets_failed_season_ids.json"
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
    """End-to-end: get season ids, fetch with retries, and replace rows per season."""
    season_brackets_table_id = manager.get_table_id("season_brackets")
    seasons_table_id = manager.get_table_id("seasons")

    season_ids_override_json = os.environ.get(SEASON_BRACKETS_IDS_JSON_ENV)
    if season_ids_override_json:
        path = Path(season_ids_override_json)
        if not path.is_file():
            raise FileNotFoundError(f"{SEASON_BRACKETS_IDS_JSON_ENV} not found: {path}")
        with open(path) as f:
            season_ids = json.load(f)
        if not isinstance(season_ids, list):
            raise TypeError(
                f"{SEASON_BRACKETS_IDS_JSON_ENV} must be a JSON list of season IDs, got {type(season_ids)}"
            )
        season_ids = [str(sid) for sid in season_ids if sid]
        season_ids = list(dict.fromkeys(season_ids))
        print(
            f"Using {len(season_ids)} season IDs from {SEASON_BRACKETS_IDS_JSON_ENV}={path}",
            flush=True,
        )
    else:
        all_season_ids = bq.get_seasons_from_seasons_table(seasons_table_id)
        completed_season_ids = set(
            bq.get_completed_season_ids_from_season_brackets_table(season_brackets_table_id)
        )
        season_ids = [sid for sid in all_season_ids if sid not in completed_season_ids]
        print(
            (
                "Season brackets scope: "
                f"all={len(all_season_ids)} completed={len(completed_season_ids)} "
                f"to_process={len(season_ids)}"
            ),
            flush=True,
        )

    failed_season_ids: list[str] = []
    failed_season_ids_seen: set[str] = set()
    failed_ids_out_path = Path(SEASON_BRACKETS_FAILED_SEASON_IDS_JSON)

    def persist_failed_season_ids() -> None:
        """Persist failed season IDs atomically so partial progress survives crashes."""
        failed_ids_out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = failed_ids_out_path.with_name(f"{failed_ids_out_path.name}.tmp")
        with open(tmp_path, "w") as f:
            json.dump(failed_season_ids, f, indent=2)
        tmp_path.replace(failed_ids_out_path)

    async def fetch_one(season_id: str) -> tuple[str, dict]:
        last_exception: Exception | None = None
        for attempt in range(1, SEASON_BRACKETS_MAX_RETRIES + 1):
            try:
                async with semaphore:
                    raw = await manager.get_raw_async("season_brackets", client, season_id=season_id)
                return (season_id, raw)
            except Exception as exc:
                last_exception = exc
                print(
                    (
                        f"\n  Fetch failed: {season_id} "
                        f"(attempt {attempt}/{SEASON_BRACKETS_MAX_RETRIES}) "
                        f"— {_describe_fetch_exception(exc)}"
                    ),
                    flush=True,
                )
                if attempt < SEASON_BRACKETS_MAX_RETRIES:
                    await asyncio.sleep(SEASON_BRACKETS_RETRY_DELAY_SECONDS * attempt)

        raise RuntimeError(
            f"Failed to fetch season brackets for {season_id} after {SEASON_BRACKETS_MAX_RETRIES} attempts."
        ) from last_exception

    total = len(season_ids)
    persist_failed_season_ids()
    print(f"Checkpointing failed season IDs to {failed_ids_out_path}", flush=True)
    pending: dict[asyncio.Task[tuple[str, dict]], str] = {}
    for season_id in season_ids:
        task = asyncio.create_task(fetch_one(season_id))
        pending[task] = season_id

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
                    f"\nError fetching season brackets after retries for {season_id}: {e}",
                    flush=True,
                )
                continue

            rows = manager.raw_to_rows("season_brackets", raw, season_id=season_id)
            bq.replace_season_brackets_rows_for_season(
                season_brackets_table_id,
                season_id,
                rows,
            )
            completed += 1
            print(f"\rSeason brackets: {completed}/{total} seasons", end="", flush=True)

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
