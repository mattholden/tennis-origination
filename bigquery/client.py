"""
BigQuery client for writing odds and related data.

Credentials (choose one):
- SSO / Application Default Credentials: run `gcloud auth application-default login`;
  do not set GOOGLE_APPLICATION_CREDENTIALS in .env.
- Service account key: set GOOGLE_APPLICATION_CREDENTIALS in .env to the key file path.

Tables (in .env):
- BIGQUERY_TABLE_ID = odds table (project_id.dataset_id.table_id)
- BIGQUERY_FIXTURES_TABLE_ID = fixtures table
"""

import os
from typing import Any

from dotenv import load_dotenv
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

load_dotenv()

BIGQUERY_TABLE_ID = os.getenv("BIGQUERY_TABLE_ID")
BIGQUERY_FIXTURES_TABLE_ID = os.getenv("BIGQUERY_FIXTURES_TABLE_ID")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")


def get_client() -> bigquery.Client:
    """
    Return a BigQuery client.
    Uses GOOGLE_APPLICATION_CREDENTIALS if set in .env; otherwise uses Application
    Default Credentials (e.g. from `gcloud auth application-default login`).
    """
    if GOOGLE_APPLICATION_CREDENTIALS:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_APPLICATION_CREDENTIALS
    return bigquery.Client()


def get_table_id() -> str:
    """Return the odds table ID. Raises if BIGQUERY_TABLE_ID is not set."""
    if not BIGQUERY_TABLE_ID:
        raise ValueError(
            "BIGQUERY_TABLE_ID is not set. Add it to .env (e.g. project_id.dataset_id.table_id)."
        )
    return BIGQUERY_TABLE_ID


def get_fixtures_table_id() -> str:
    """Return the fixtures table ID. Raises if BIGQUERY_FIXTURES_TABLE_ID is not set."""
    if not BIGQUERY_FIXTURES_TABLE_ID:
        raise ValueError(
            "BIGQUERY_FIXTURES_TABLE_ID is not set. Add it to .env."
        )
    return BIGQUERY_FIXTURES_TABLE_ID


def create_table_if_not_exists(table_id: str | None = None) -> bool:
    """
    Create the tennis OddsJam odds table only if it does not exist.
    The dataset must already exist. Returns True if created, False if already existed.
    """
    from bigquery.schema import get_odds_table_schema

    target = table_id or get_table_id()
    client = get_client()
    try:
        client.get_table(target)
        return False
    except NotFound:
        pass
    table = bigquery.Table(target, schema=get_odds_table_schema())
    client.create_table(table)
    return True


def create_fixtures_table_if_not_exists(table_id: str | None = None) -> bool:
    """
    Create the tennis fixtures table only if it does not exist.
    The dataset must already exist. Returns True if created, False if already existed.
    """
    from bigquery.schema import get_fixtures_table_schema

    target = table_id or get_fixtures_table_id()
    client = get_client()
    try:
        client.get_table(target)
        return False
    except NotFound:
        pass
    table = bigquery.Table(target, schema=get_fixtures_table_schema())
    client.create_table(table)
    return True


def write_rows(rows: list[dict[str, Any]], table_id: str | None = None) -> int:
    """Insert rows into the configured BigQuery table via streaming insert."""
    target = table_id or get_table_id()
    client = get_client()
    errors = client.insert_rows_json(target, rows)
    if errors:
        raise RuntimeError(f"BigQuery insert_rows_json failed: {errors}")
    return len(rows)
