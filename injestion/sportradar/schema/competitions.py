"""
Competitions table: BigQuery schema and transform (raw payload -> rows).
"""

from typing import Optional

from google.cloud import bigquery


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema for the competitions table (flattened)."""
    return [
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("gender", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("category_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("category_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("level", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("parent_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("generated_at", "TIMESTAMP", mode="NULLABLE"),
    ]


def row_to_bq(
    record: dict,
    *,
    generated_at: Optional[str] = None,
) -> dict:
    """One raw competition -> one flat row for BigQuery."""
    category = record.get("category") or {}
    return {
        "id": record.get("id"),
        "name": record.get("name"),
        "type": record.get("type"),
        "gender": record.get("gender"),
        "category_id": category.get("id"),
        "category_name": category.get("name"),
        "level": record.get("level"),
        "parent_id": record.get("parent_id"),
        "generated_at": generated_at,
    }


def payload_to_rows(raw: dict) -> list[dict]:
    """
    Full API response -> list of rows.
    Invokes row_to_bq for each competition; runner never calls row_to_bq directly.
    """
    generated_at = raw.get("generated_at")
    return [
        row_to_bq(r, generated_at=generated_at)
        for r in raw.get("competitions") or []
    ]
