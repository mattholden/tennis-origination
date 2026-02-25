"""
OddsJam odds table: BigQuery schema and transform (raw payload -> rows).
"""

from typing import Any

from google.cloud import bigquery


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema for the oddsjam_odds table."""
    pass

def payload_to_rows(raw: dict) -> list[dict]:
    """Transform raw payload to rows."""
    pass

def odds_row_to_bq(row: dict[str, Any]) -> dict[str, Any]:
    """Convert one odds record from oddsjam_odds.json into a flat dict for BigQuery."""
    pass