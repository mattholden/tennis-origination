"""
Minimal BigQuery interface for pipelines: write_rows and get_param_list.

Pipelines use this to upload data and to read parameter lists (e.g. season_ids
from the seasons table) for parameterized resources. Credentials via
GOOGLE_APPLICATION_CREDENTIALS or Application Default Credentials.
"""

import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from google.api_core import exceptions as gapi_exceptions
from google.cloud import bigquery


def get_client() -> bigquery.Client:
    """Return a BigQuery client. Uses GOOGLE_APPLICATION_CREDENTIALS if set."""
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
    return bigquery.Client()


def write_rows(table_id: str, rows: list[dict[str, Any]]) -> int:
    """Stream insert rows into the given table. Returns number of rows. Raises on any insert error."""
    if not rows:
        return 0
    client = get_client()
    errors = client.insert_rows_json(table_id, rows)
    if errors:
        sample = errors[:3] if len(errors) > 3 else errors
        raise RuntimeError(
            f"BigQuery insert_rows_json failed (table={table_id}, {len(errors)} errors): {sample}"
        )
    return len(rows)


def merge_odds_rows_by_odds_id(table_id: str, rows: list[dict[str, Any]]) -> dict[str, int]:
    """
    Insert OddsJam odds rows with dedupe on odds_id.

    Behavior:
    - rows with non-null odds_id are merged on odds_id (insert when not matched)
    - rows with null odds_id and non-null fixture_id are merged on fixture_id
      (insert when fixture_id not already present in target)
    - rows with null odds_id and null fixture_id are inserted as-is

    Returns counts for observability.
    """
    if not rows:
        return {
            "input_rows": 0,
            "source_keyed_rows": 0,
            "source_non_key_rows": 0,
            "source_keyed_rows_deduped": 0,
            "source_non_key_rows_with_fixture_id": 0,
            "source_non_key_rows_with_fixture_id_deduped": 0,
            "source_non_key_rows_without_fixture_id": 0,
            "inserted_keyed_rows": 0,
            "inserted_non_key_rows_with_fixture_id": 0,
            "inserted_non_key_rows_without_fixture_id": 0,
            "inserted_non_key_rows": 0,
            "total_inserted_rows": 0,
        }

    keyed_rows: list[dict[str, Any]] = []
    non_key_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("odds_id") is None:
            non_key_rows.append(row)
        else:
            keyed_rows.append(row)

    # Dedupe incoming keyed rows by odds_id so MERGE source has unique keys.
    deduped_by_odds_id: dict[str, dict[str, Any]] = {}
    for row in keyed_rows:
        deduped_by_odds_id[str(row["odds_id"])] = row
    keyed_rows_deduped = list(deduped_by_odds_id.values())

    non_key_rows_with_fixture_id = [row for row in non_key_rows if row.get("fixture_id") is not None]
    non_key_rows_without_fixture_id = [row for row in non_key_rows if row.get("fixture_id") is None]

    deduped_non_key_by_fixture_id: dict[str, dict[str, Any]] = {}
    for row in non_key_rows_with_fixture_id:
        deduped_non_key_by_fixture_id[str(row["fixture_id"])] = row
    non_key_rows_with_fixture_id_deduped = list(deduped_non_key_by_fixture_id.values())

    client: bigquery.Client | None = None
    target_table: bigquery.Table | None = None
    target_cols: list[str] | None = None

    def _get_target_metadata() -> tuple[bigquery.Client, bigquery.Table, list[str]]:
        nonlocal client, target_table, target_cols
        if client is None or target_table is None or target_cols is None:
            client = get_client()
            target_table = client.get_table(table_id)
            target_cols = [field.name for field in target_table.schema]
        return client, target_table, target_cols

    def _merge_insert_only(source_rows: list[dict[str, Any]], key_column: str, temp_suffix: str) -> int:
        if not source_rows:
            return 0
        merge_client, merge_target_table, merge_target_cols = _get_target_metadata()
        temp_table_id = (
            f"{merge_target_table.project}.{merge_target_table.dataset_id}."
            f"_tmp_odds_merge_{temp_suffix}_{uuid.uuid4().hex[:12]}"
        )

        temp_table = bigquery.Table(temp_table_id, schema=merge_target_table.schema)
        temp_table.expires = datetime.now(timezone.utc) + timedelta(hours=1)

        insert_cols_sql = ", ".join(f"`{c}`" for c in merge_target_cols)
        insert_vals_sql = ", ".join(f"S.`{c}`" for c in merge_target_cols)
        merge_sql = f"""
MERGE `{table_id}` T
USING `{temp_table_id}` S
ON T.`{key_column}` = S.`{key_column}`
WHEN NOT MATCHED BY TARGET THEN
  INSERT ({insert_cols_sql})
  VALUES ({insert_vals_sql})
"""
        max_attempts = 3
        try:
            for attempt in range(1, max_attempts + 1):
                try:
                    # exists_ok handles rare retries where the table was created but timing/visibility lagged.
                    merge_client.create_table(temp_table, exists_ok=True)

                    errors = merge_client.insert_rows_json(temp_table_id, source_rows)
                    if errors:
                        sample = errors[:3] if len(errors) > 3 else errors
                        raise RuntimeError(
                            "BigQuery insert_rows_json failed for odds merge staging "
                            f"(table={temp_table_id}, {len(errors)} errors): {sample}"
                        )

                    job = merge_client.query(merge_sql)
                    job.result()
                    return int(job.num_dml_affected_rows or 0)
                except gapi_exceptions.NotFound as e:
                    if attempt == max_attempts:
                        raise
                    print(
                        (
                            f"  Staging table not found for odds merge ({temp_table_id}) "
                            f"on attempt {attempt}/{max_attempts}; retrying."
                        ),
                        flush=True,
                    )
                    merge_client.delete_table(temp_table_id, not_found_ok=True)
                    time.sleep(0.5 * attempt)
        finally:
            merge_client.delete_table(temp_table_id, not_found_ok=True)

    inserted_keyed_rows = _merge_insert_only(keyed_rows_deduped, "odds_id", "odds_id")
    inserted_non_key_rows_with_fixture_id = _merge_insert_only(
        non_key_rows_with_fixture_id_deduped, "fixture_id", "fixture_id"
    )
    inserted_non_key_rows_without_fixture_id = (
        write_rows(table_id, non_key_rows_without_fixture_id) if non_key_rows_without_fixture_id else 0
    )
    inserted_non_key_rows = (
        inserted_non_key_rows_with_fixture_id + inserted_non_key_rows_without_fixture_id
    )
    total_inserted_rows = inserted_keyed_rows + inserted_non_key_rows
    return {
        "input_rows": len(rows),
        "source_keyed_rows": len(keyed_rows),
        "source_non_key_rows": len(non_key_rows),
        "source_keyed_rows_deduped": len(keyed_rows_deduped),
        "source_non_key_rows_with_fixture_id": len(non_key_rows_with_fixture_id),
        "source_non_key_rows_with_fixture_id_deduped": len(non_key_rows_with_fixture_id_deduped),
        "source_non_key_rows_without_fixture_id": len(non_key_rows_without_fixture_id),
        "inserted_keyed_rows": inserted_keyed_rows,
        "inserted_non_key_rows_with_fixture_id": inserted_non_key_rows_with_fixture_id,
        "inserted_non_key_rows_without_fixture_id": inserted_non_key_rows_without_fixture_id,
        "inserted_non_key_rows": inserted_non_key_rows,
        "total_inserted_rows": total_inserted_rows,
    }


def delete_stale_no_odds_rows_for_fixtures(
    table_id: str,
    fixture_ids: list[str],
    *,
    chunk_size: int = 5000,
) -> int:
    """
    Delete stale no-odds sentinel rows for the given fixtures.

    A row is considered stale when:
    - odds_id is NULL
    - no_odds is true
    - the same fixture_id now has at least one row with non-null odds_id

    The delete is scoped to the fixture_ids passed in and chunked to avoid
    oversized query parameters. Returns total deleted rows across all chunks.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be > 0, got {chunk_size}")

    normalized_ids = [str(fid) for fid in fixture_ids if fid]
    if not normalized_ids:
        return 0
    # Preserve order while deduping.
    deduped_ids = list(dict.fromkeys(normalized_ids))

    client = get_client()
    total_deleted = 0
    sql = f"""
DELETE FROM `{table_id}` T
WHERE T.fixture_id IN UNNEST(@fixture_ids)
  AND T.odds_id IS NULL
  AND IFNULL(T.no_odds, FALSE) = TRUE
  AND EXISTS (
    SELECT 1
    FROM `{table_id}` R
    WHERE R.fixture_id = T.fixture_id
      AND R.odds_id IS NOT NULL
  )
"""
    for i in range(0, len(deduped_ids), chunk_size):
        chunk = deduped_ids[i : i + chunk_size]
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("fixture_ids", "STRING", chunk),
            ]
        )
        job = client.query(sql, job_config=job_config)
        job.result()
        total_deleted += int(job.num_dml_affected_rows or 0)
    return total_deleted


def merge_fixture_rows_by_fixture_id(table_id: str, rows: list[dict[str, Any]]) -> dict[str, int]:
    """
    Insert fixture rows with dedupe on fixture id.

    Behavior:
    - rows with non-null id are merged on id (insert when not matched)
    - rows with null id are inserted as-is

    Returns counts for observability.
    """
    if not rows:
        return {
            "input_rows": 0,
            "source_keyed_rows": 0,
            "source_non_key_rows": 0,
            "source_keyed_rows_deduped": 0,
            "inserted_keyed_rows": 0,
            "inserted_non_key_rows": 0,
            "total_inserted_rows": 0,
        }

    keyed_rows: list[dict[str, Any]] = []
    non_key_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("id") is None:
            non_key_rows.append(row)
        else:
            keyed_rows.append(row)

    # Dedupe incoming keyed rows by fixture id so MERGE source has unique keys.
    deduped_by_fixture_id: dict[str, dict[str, Any]] = {}
    for row in keyed_rows:
        deduped_by_fixture_id[str(row["id"])] = row
    keyed_rows_deduped = list(deduped_by_fixture_id.values())

    inserted_keyed_rows = 0
    if keyed_rows_deduped:
        client = get_client()
        target_table = client.get_table(table_id)
        temp_table_id = (
            f"{target_table.project}.{target_table.dataset_id}."
            f"_tmp_fixture_merge_{uuid.uuid4().hex[:12]}"
        )

        temp_table = bigquery.Table(temp_table_id, schema=target_table.schema)
        temp_table.expires = datetime.now(timezone.utc) + timedelta(hours=1)
        target_cols = [field.name for field in target_table.schema]
        insert_cols_sql = ", ".join(f"`{c}`" for c in target_cols)
        insert_vals_sql = ", ".join(f"S.`{c}`" for c in target_cols)
        merge_sql = f"""
MERGE `{table_id}` T
USING `{temp_table_id}` S
ON T.id = S.id
WHEN NOT MATCHED BY TARGET THEN
  INSERT ({insert_cols_sql})
  VALUES ({insert_vals_sql})
"""
        max_attempts = 3

        try:
            for attempt in range(1, max_attempts + 1):
                try:
                    client.create_table(temp_table, exists_ok=True)

                    errors = client.insert_rows_json(temp_table_id, keyed_rows_deduped)
                    if errors:
                        sample = errors[:3] if len(errors) > 3 else errors
                        raise RuntimeError(
                            "BigQuery insert_rows_json failed for fixture merge staging "
                            f"(table={temp_table_id}, {len(errors)} errors): {sample}"
                        )

                    job = client.query(merge_sql)
                    job.result()
                    inserted_keyed_rows = int(job.num_dml_affected_rows or 0)
                    break
                except gapi_exceptions.NotFound:
                    if attempt == max_attempts:
                        raise
                    print(
                        (
                            f"  Staging table not found for fixture merge ({temp_table_id}) "
                            f"on attempt {attempt}/{max_attempts}; retrying."
                        ),
                        flush=True,
                    )
                    client.delete_table(temp_table_id, not_found_ok=True)
                    time.sleep(0.5 * attempt)
        finally:
            client.delete_table(temp_table_id, not_found_ok=True)

    inserted_non_key_rows = write_rows(table_id, non_key_rows) if non_key_rows else 0
    total_inserted_rows = inserted_keyed_rows + inserted_non_key_rows
    return {
        "input_rows": len(rows),
        "source_keyed_rows": len(keyed_rows),
        "source_non_key_rows": len(non_key_rows),
        "source_keyed_rows_deduped": len(keyed_rows_deduped),
        "inserted_keyed_rows": inserted_keyed_rows,
        "inserted_non_key_rows": inserted_non_key_rows,
        "total_inserted_rows": total_inserted_rows,
    }


def get_param_list(table_id: str, column: str) -> list[Any]:
    """
    Query the table for distinct values of one column. Use for parameterized
    pipelines (e.g. season_id from seasons table).
    Returns list of non-null values; order not guaranteed.
    """
    client = get_client()
    # Table id is project.dataset.table; quote for safe SQL
    sql = f'SELECT DISTINCT `{column}` FROM `{table_id}`'
    job = client.query(sql)
    return [row[column] for row in job.result() if row[column] is not None]


def get_competition_ids_from_competitions_table(competitions_table_id: str) -> frozenset[str]:
    """
    Return the set of competition ids stored in the competitions table.
    Used by the seasons pipeline to filter seasons to only those whose
    competition_id exists in our competitions table (ATP, WTA, Davis Cup, BJK Cup).
    """
    client = get_client()
    sql = f'SELECT DISTINCT id FROM `{competitions_table_id}`'
    job = client.query(sql)
    return frozenset(row["id"] for row in job.result() if row["id"] is not None)

def get_seasons_from_seasons_table(seasons_table_id: str) -> frozenset[str]:
    """
    Return the set of season ids stored in the seasons table.
    """
    client = get_client()
    sql = f'SELECT DISTINCT id FROM `{seasons_table_id}`'
    job = client.query(sql)
    return frozenset(row["id"] for row in job.result() if row["id"] is not None)

def get_major_competition_ids() -> frozenset[str]:
    """
    Return the set of competition ids for the major tournaments (Grand Slams, ATP Finals, WTA Finals, Davis Cup, BJK Cup).
    Used by the seasons pipeline to filter seasons to only those whose
    competition_id exists in our competitions table (ATP, WTA, Davis Cup, BJK Cup).
    """
    return frozenset({
        "sr:competition:2567", # Australian Open men's singles
        "sr:competition:2579", # French Open men's singles
        "sr:competition:2555", # Wimbledon men's singles
        "sr:competition:2591", # US Open men's singles
        "sr:competition:2571", # Australian Open women's singles
        "sr:competition:2583", # French Open women's singles
        "sr:competition:2559", # Wimbledon women's singles
        "sr:competition:2595", # US Open women's singles
    })

def get_season_ids_for_major_competitions(seasons_table_id: str) -> list[str]:
    """
    Return the list of season ids for the major tournaments (Grand Slams only for now).
    Used by the season competitors pipeline to fetch competitors for a test subset.
    """
    major_ids = get_major_competition_ids()
    major_ids_list = ", ".join(repr(cid) for cid in major_ids)  # e.g. 'sr:competition:2567', ...
    client = get_client()
    sql = f"SELECT DISTINCT id FROM `{seasons_table_id}` WHERE competition_id IN ({major_ids_list})"
    job = client.query(sql)
    return [row["id"] for row in job.result() if row["id"] is not None]

def get_competitor_ids_from_season_competitors_table(season_competitors_table_id: str) -> list[str]:
    """
    Return the list of competitor ids stored in the season competitors table.
    Used by the competitors pipeline to fetch competitors for a test subset.
    """
    client = get_client()
    sql = f'SELECT DISTINCT competitor_id FROM `{season_competitors_table_id}`'
    job = client.query(sql)
    return [row["competitor_id"] for row in job.result() if row["competitor_id"] is not None]

def get_sport_event_ids_from_season_brackets_table(season_brackets_table_id: str) -> list[str]:
    """
    Return the list of sport event ids stored in the season brackets table.
    Used by the event summaries pipeline to fetch summaries for a test subset.
    """
    client = get_client()
    sql = f'SELECT DISTINCT sport_event_id FROM `{season_brackets_table_id}`'
    job = client.query(sql)
    return [row["sport_event_id"] for row in job.result() if row["sport_event_id"] is not None]


def get_fixture_ids_from_oddsjam_fixtures_table(fixtures_table_id: str) -> list[str]:
    """
    Return the list of fixture ids from the OddsJam fixtures table.
    Used by the odds pipeline to fetch odds for all fixtures in parallel.
    """
    client = get_client()
    sql = f'SELECT DISTINCT id FROM `{fixtures_table_id}`'
    job = client.query(sql)
    return [row["id"] for row in job.result() if row["id"] is not None]

def get_existing_season_ids_from_season_brackets_table(season_brackets_table_id: str) -> list[str]:
    """
    Return the list of season ids from the season brackets table.
    Used by the season_brackets pipeline to skip already-fetched seasons.
    """
    client = get_client()
    sql = f'SELECT DISTINCT season_id FROM `{season_brackets_table_id}`'
    job = client.query(sql)
    return [row["season_id"] for row in job.result() if row["season_id"] is not None]

def get_existing_sport_event_ids_from_event_summary_table(event_summary_table_id: str) -> list[str]:
    """
    Return the list of sport event ids from the event summary table.
    Used by the event summaries pipeline to skip already-fetched sport events.
    """
    client = get_client()
    sql = f'SELECT DISTINCT sport_event_id FROM `{event_summary_table_id}`'
    job = client.query(sql)
    return [row["sport_event_id"] for row in job.result() if row["sport_event_id"] is not None]
