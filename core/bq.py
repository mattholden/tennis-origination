"""
Minimal BigQuery interface for pipelines: write_rows and get_param_list.

Pipelines use this to upload data and to read parameter lists (e.g. season_ids
from the seasons table) for parameterized resources. Credentials via
GOOGLE_APPLICATION_CREDENTIALS or Application Default Credentials.
"""

import os
from typing import Any

from google.cloud import bigquery


def get_client() -> bigquery.Client:
    """Return a BigQuery client. Uses GOOGLE_APPLICATION_CREDENTIALS if set."""
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
    return bigquery.Client()


def write_rows(table_id: str, rows: list[dict[str, Any]]) -> int:
    """Stream insert rows into the given table. Returns number of rows."""
    if not rows:
        return 0
    client = get_client()
    errors = client.insert_rows_json(table_id, rows)
    if errors:
        raise RuntimeError(f"BigQuery insert_rows_json failed: {errors}")
    return len(rows)


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
