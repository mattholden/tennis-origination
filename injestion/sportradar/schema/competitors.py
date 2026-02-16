"""
Competitors table: BigQuery schema and transform (raw payload -> rows).
"""

from typing import Optional

from google.cloud import bigquery


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema for the competitors table (flattened, one row per competitor)."""
    pass

def payload_to_rows(raw: dict) -> list[dict]:
    """Transform raw payload to rows (same as load_resource but without fetch)."""
    pass

def row_to_bq(record: dict, *, generated_at: Optional[str] = None) -> dict:
    """One raw competitor -> one flat row for BigQuery."""
    pass