"""
Competitions table: BigQuery schema and transform (raw payload -> rows).

Raw API shape:
  { "generated_at": "ISO8601", "competitions": [ {...}, ... ] }
  Each competition: id, name, type (singles|doubles|mixed_doubles|mixed), gender (men|women|mixed),
  category { id, name }, optional level (grand_slam|atp_1000|...), optional parent_id.
We only store competitions whose category.id is in ALLOWED_CATEGORY_IDS (ATP, WTA, Davis Cup, BJK Cup).
"""

from typing import Optional

from google.cloud import bigquery

# ATP, WTA, Davis Cup, Billie Jean King Cup — only these competitions are stored
ALLOWED_CATEGORY_IDS = frozenset({
    "sr:category:3",   # ATP
    "sr:category:6",   # WTA
    "sr:category:76",  # Davis Cup
    "sr:category:74",  # Billie Jean King Cup
})


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema for the competitions table (flattened, one row per competition)."""
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
    Full API response -> list of rows. Only includes competitions whose
    category.id is in ALLOWED_CATEGORY_IDS (ATP, WTA, Davis Cup, Billie Jean King Cup).
    """
    generated_at = raw.get("generated_at")
    competitions = raw.get("competitions") or []
    return [
        row_to_bq(r, generated_at=generated_at)
        for r in competitions
        if (r.get("category") or {}).get("id") in ALLOWED_CATEGORY_IDS
    ]
