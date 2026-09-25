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


def _infer_project_from_table_env() -> str | None:
    """Infer GCP project from any BIGQUERY_* table id (project.dataset.table)."""
    for key, value in os.environ.items():
        if not key.startswith("BIGQUERY_") or not value:
            continue
        table_id = value.strip().strip('"').strip("'")
        parts = table_id.split(".")
        if len(parts) >= 3 and parts[0]:
            return parts[0]
    return None


def get_client() -> bigquery.Client:
    """
    Return a BigQuery client.

    Loads project-root `.env` (via load_env), then resolves project from
    GOOGLE_CLOUD_PROJECT / GCLOUD_PROJECT, or by inferring from BIGQUERY_* table ids.
    Credentials use GOOGLE_APPLICATION_CREDENTIALS if set, otherwise ADC.
    """
    from injestion.core.env import load_env

    load_env()

    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCLOUD_PROJECT")
        or _infer_project_from_table_env()
    )
    if project:
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project)
        return bigquery.Client(project=project)
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


def _write_rows_in_chunks(
    table_id: str,
    rows: list[dict[str, Any]],
    *,
    chunk_size: int = 2000,
) -> int:
    """Insert rows in bounded chunks to keep request payloads manageable."""
    if not rows:
        return 0
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")

    inserted_rows = 0
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        inserted_rows += write_rows(table_id, chunk)
    return inserted_rows


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


def merge_season_competitor_rows_by_season_and_competitor(
    table_id: str,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """
    Insert season competitor rows with dedupe on (season_id, competitor_id).

    Behavior:
    - rows with non-null season_id and competitor_id are merged on the composite key
      (insert when not matched)
    - rows missing either key are dropped

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
            "dropped_non_key_rows": 0,
            "total_inserted_rows": 0,
        }

    keyed_rows: list[dict[str, Any]] = []
    non_key_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("season_id") is None or row.get("competitor_id") is None:
            non_key_rows.append(row)
        else:
            keyed_rows.append(row)

    # Dedupe incoming keyed rows by (season_id, competitor_id) so MERGE source has unique keys.
    deduped_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in keyed_rows:
        key = (str(row["season_id"]), str(row["competitor_id"]))
        deduped_by_key[key] = row
    keyed_rows_deduped = list(deduped_by_key.values())

    inserted_keyed_rows = 0
    if keyed_rows_deduped:
        client = get_client()
        target_table = client.get_table(table_id)
        temp_table_id = (
            f"{target_table.project}.{target_table.dataset_id}."
            f"_tmp_season_competitors_merge_{uuid.uuid4().hex[:12]}"
        )

        temp_table = bigquery.Table(temp_table_id, schema=target_table.schema)
        temp_table.expires = datetime.now(timezone.utc) + timedelta(hours=1)
        target_cols = [field.name for field in target_table.schema]
        insert_cols_sql = ", ".join(f"`{c}`" for c in target_cols)
        insert_vals_sql = ", ".join(f"S.`{c}`" for c in target_cols)
        merge_sql = f"""
MERGE `{table_id}` T
USING `{temp_table_id}` S
ON T.season_id = S.season_id
AND T.competitor_id = S.competitor_id
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
                            "BigQuery insert_rows_json failed for season competitors merge staging "
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
                            "  Staging table not found for season competitors merge "
                            f"({temp_table_id}) on attempt {attempt}/{max_attempts}; retrying."
                        ),
                        flush=True,
                    )
                    client.delete_table(temp_table_id, not_found_ok=True)
                    time.sleep(0.5 * attempt)
        finally:
            client.delete_table(temp_table_id, not_found_ok=True)

    inserted_non_key_rows = 0
    dropped_non_key_rows = len(non_key_rows)
    total_inserted_rows = inserted_keyed_rows + inserted_non_key_rows
    return {
        "input_rows": len(rows),
        "source_keyed_rows": len(keyed_rows),
        "source_non_key_rows": len(non_key_rows),
        "source_keyed_rows_deduped": len(keyed_rows_deduped),
        "inserted_keyed_rows": inserted_keyed_rows,
        "inserted_non_key_rows": inserted_non_key_rows,
        "dropped_non_key_rows": dropped_non_key_rows,
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


def get_season_ids_from_seasons_table_by_min_start_date(
    seasons_table_id: str,
    *,
    min_start_date: str,
) -> list[str]:
    """
    Return season ids whose start_date is between min_start_date and today.

    min_start_date should be an ISO date string (YYYY-MM-DD).
    """
    client = get_client()
    sql = f"""
SELECT DISTINCT id
FROM `{seasons_table_id}`
WHERE id IS NOT NULL
  AND start_date IS NOT NULL
  AND start_date >= @min_start_date
  AND start_date <= CURRENT_DATE()
"""
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("min_start_date", "DATE", min_start_date),
        ]
    )
    job = client.query(sql, job_config=job_config)
    return [row["id"] for row in job.result() if row["id"] is not None]

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


def get_fixture_ids_missing_odds_rows(fixtures_table_id: str, odds_table_id: str) -> list[str]:
    """
    Return fixture ids present in fixtures table but missing from odds table.

    A fixture is considered "already processed" if any odds-table row exists for it
    (including a no-odds sentinel row).
    """
    client = get_client()
    sql = f"""
SELECT DISTINCT f.id
FROM `{fixtures_table_id}` f
LEFT JOIN (
  SELECT DISTINCT fixture_id
  FROM `{odds_table_id}`
  WHERE fixture_id IS NOT NULL
) o
ON f.id = o.fixture_id
WHERE f.id IS NOT NULL
  AND o.fixture_id IS NULL
"""
    job = client.query(sql)
    return [row["id"] for row in job.result() if row["id"] is not None]


def get_fixture_ids_missing_results_rows(odds_table_id: str, results_table_id: str) -> list[str]:
    """
    Return fixture ids present in odds table but missing from results table.
    """
    client = get_client()
    sql = f"""
SELECT DISTINCT o.fixture_id
FROM `{odds_table_id}` o
LEFT JOIN (
  SELECT DISTINCT fixture_id
  FROM `{results_table_id}`
  WHERE fixture_id IS NOT NULL
) r
ON o.fixture_id = r.fixture_id
WHERE o.fixture_id IS NOT NULL
  AND r.fixture_id IS NULL
"""
    job = client.query(sql)
    return [row["fixture_id"] for row in job.result() if row["fixture_id"] is not None]


def get_max_start_date_from_oddsjam_fixtures_table(
    fixtures_table_id: str,
    *,
    league_name: str | None = None,
) -> datetime | None:
    """
    Return MAX(start_date) from the fixtures table, optionally scoped by league.

    Returns None when the table is empty or does not exist yet.
    """
    client = get_client()
    if league_name:
        sql = f"""
SELECT MAX(start_date) AS max_start_date
FROM `{fixtures_table_id}`
WHERE UPPER(league_name) = UPPER(@league_name)
"""
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("league_name", "STRING", league_name),
            ]
        )
    else:
        sql = f"SELECT MAX(start_date) AS max_start_date FROM `{fixtures_table_id}`"
        job_config = None

    try:
        job = client.query(sql, job_config=job_config)
        rows = list(job.result())
    except gapi_exceptions.NotFound:
        return None

    if not rows:
        return None
    max_start_date = rows[0]["max_start_date"]
    if max_start_date is None:
        return None
    return max_start_date

def get_existing_season_ids_from_season_brackets_table(season_brackets_table_id: str) -> list[str]:
    """
    Return the list of season ids from the season brackets table.
    Used by the season_brackets pipeline to skip already-fetched seasons.
    """
    client = get_client()
    sql = f'SELECT DISTINCT season_id FROM `{season_brackets_table_id}`'
    job = client.query(sql)
    return [row["season_id"] for row in job.result() if row["season_id"] is not None]


def get_completed_season_ids_from_season_brackets_table(season_brackets_table_id: str) -> list[str]:
    """
    Return season ids that have at least one actual bracket row.

    A season is considered completed when it has at least one row with
    non-null cup_round_id. Placeholder rows (all-null bracket fields) do not
    mark the season as completed.
    """
    client = get_client()
    sql = f"""
SELECT DISTINCT season_id
FROM `{season_brackets_table_id}`
WHERE season_id IS NOT NULL
  AND cup_round_id IS NOT NULL
"""
    job = client.query(sql)
    return [row["season_id"] for row in job.result() if row["season_id"] is not None]


def replace_season_brackets_rows_for_season(
    table_id: str,
    season_id: str,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """
    Replace all season_brackets rows for one season with the provided rows.

    Intended for seasons that are not yet completed (e.g. placeholder rows).
    """
    if not season_id:
        raise ValueError("season_id is required to replace season_brackets rows.")

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        row_copy = dict(row)
        row_copy["season_id"] = season_id
        normalized_rows.append(row_copy)

    client = get_client()
    delete_sql = f"DELETE FROM `{table_id}` WHERE season_id = @season_id"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("season_id", "STRING", season_id),
        ]
    )
    delete_job = client.query(delete_sql, job_config=job_config)
    delete_job.result()
    deleted_rows = int(delete_job.num_dml_affected_rows or 0)

    inserted_rows = _write_rows_in_chunks(table_id, normalized_rows, chunk_size=2000)
    return {
        "input_rows": len(rows),
        "deleted_rows": deleted_rows,
        "inserted_rows": inserted_rows,
    }


def get_sport_event_ids_for_event_summary_processing(
    season_brackets_table_id: str,
    event_summary_table_id: str,
    *,
    terminal_match_statuses: tuple[str, ...] = ("ended", "retired", "walkover"),
) -> list[str]:
    """
    Return sport_event_ids that should be processed by the event_summary pipeline.

    Candidate IDs come from season_brackets. An ID is selected when:
    - no summary row exists yet, or
    - at least one sparse summary row exists, or
    - at least one non-terminal/unknown match_status row exists.
    """
    client = get_client()
    sql = f"""
WITH bracket_ids AS (
  SELECT DISTINCT sport_event_id
  FROM `{season_brackets_table_id}`
  WHERE sport_event_id IS NOT NULL
),
summary_status AS (
  SELECT
    sport_event_id,
    LOGICAL_OR(
      generated_at IS NULL
      AND competition_id IS NULL
      AND season_id IS NULL
      AND start_time IS NULL
      AND match_status IS NULL
    ) AS has_sparse_row,
    LOGICAL_OR(
      match_status IS NULL
      OR LOWER(match_status) NOT IN UNNEST(@terminal_statuses)
    ) AS has_non_terminal_row
  FROM `{event_summary_table_id}`
  WHERE sport_event_id IS NOT NULL
  GROUP BY sport_event_id
)
SELECT b.sport_event_id
FROM bracket_ids b
LEFT JOIN summary_status s
ON b.sport_event_id = s.sport_event_id
WHERE s.sport_event_id IS NULL
   OR s.has_sparse_row
   OR s.has_non_terminal_row
"""
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter(
                "terminal_statuses",
                "STRING",
                [status.lower() for status in terminal_match_statuses],
            ),
        ]
    )
    job = client.query(sql, job_config=job_config)
    return [row["sport_event_id"] for row in job.result() if row["sport_event_id"] is not None]


def _replace_rows_for_sport_event_id(
    table_id: str,
    sport_event_id: str,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Replace all rows for one sport_event_id with provided rows."""
    if not sport_event_id:
        raise ValueError("sport_event_id is required to replace rows.")

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        row_copy = dict(row)
        row_copy["sport_event_id"] = sport_event_id
        normalized_rows.append(row_copy)

    client = get_client()
    delete_sql = f"DELETE FROM `{table_id}` WHERE sport_event_id = @sport_event_id"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("sport_event_id", "STRING", sport_event_id),
        ]
    )
    delete_job = client.query(delete_sql, job_config=job_config)
    delete_job.result()
    deleted_rows = int(delete_job.num_dml_affected_rows or 0)

    inserted_rows = write_rows(table_id, normalized_rows) if normalized_rows else 0
    return {
        "input_rows": len(rows),
        "deleted_rows": deleted_rows,
        "inserted_rows": inserted_rows,
    }


def _replace_rows_for_sport_event_ids(
    table_id: str,
    sport_event_ids: list[str],
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Replace all rows for a cohort of sport_event_ids with provided rows."""
    normalized_event_ids = [str(eid) for eid in sport_event_ids if eid]
    # Preserve order while deduping.
    normalized_event_ids = list(dict.fromkeys(normalized_event_ids))
    if not normalized_event_ids:
        raise ValueError("sport_event_ids is required to replace rows.")

    client = get_client()
    delete_sql = f"""
DELETE FROM `{table_id}`
WHERE sport_event_id IN UNNEST(@sport_event_ids)
"""
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter(
                "sport_event_ids",
                "STRING",
                normalized_event_ids,
            ),
        ]
    )
    delete_job = client.query(delete_sql, job_config=job_config)
    delete_job.result()
    deleted_rows = int(delete_job.num_dml_affected_rows or 0)

    inserted_rows = _write_rows_in_chunks(table_id, rows, chunk_size=2000)
    return {
        "input_rows": len(rows),
        "cohort_size": len(normalized_event_ids),
        "deleted_rows": deleted_rows,
        "inserted_rows": inserted_rows,
    }


def replace_event_summary_rows_for_event(
    table_id: str,
    sport_event_id: str,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Replace event_summary rows for one sport_event_id."""
    return _replace_rows_for_sport_event_id(table_id, sport_event_id, rows)


def replace_event_statistics_rows_for_event(
    table_id: str,
    sport_event_id: str,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Replace event_statistics rows for one sport_event_id."""
    return _replace_rows_for_sport_event_id(table_id, sport_event_id, rows)


def replace_event_timeline_rows_for_event(
    table_id: str,
    sport_event_id: str,
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Replace event_timeline rows for one sport_event_id."""
    return _replace_rows_for_sport_event_id(table_id, sport_event_id, rows)


def replace_event_summary_rows_for_events(
    table_id: str,
    sport_event_ids: list[str],
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Replace event_summary rows for a cohort of sport_event_ids."""
    return _replace_rows_for_sport_event_ids(table_id, sport_event_ids, rows)


def replace_event_statistics_rows_for_events(
    table_id: str,
    sport_event_ids: list[str],
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Replace event_statistics rows for a cohort of sport_event_ids."""
    return _replace_rows_for_sport_event_ids(table_id, sport_event_ids, rows)


def replace_event_timeline_rows_for_events(
    table_id: str,
    sport_event_ids: list[str],
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Replace event_timeline rows for a cohort of sport_event_ids."""
    return _replace_rows_for_sport_event_ids(table_id, sport_event_ids, rows)


def get_existing_sport_event_ids_from_event_summary_table(event_summary_table_id: str) -> list[str]:
    """
    Return the list of sport event ids from the event summary table.
    Used by the event summaries pipeline to skip already-fetched sport events.
    """
    client = get_client()
    sql = f'SELECT DISTINCT sport_event_id FROM `{event_summary_table_id}`'
    job = client.query(sql)
    return [row["sport_event_id"] for row in job.result() if row["sport_event_id"] is not None]
