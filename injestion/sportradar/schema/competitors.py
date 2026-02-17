"""
Competitors table: BigQuery schema and transform (raw payload -> rows).
"""

import re
from typing import Any, Optional

from google.cloud import bigquery


def _timestamp_for_bq(iso_str: Optional[str]) -> Optional[str]:
    """Convert ISO8601 (e.g. 2026-02-16T03:21:59+00:00) to BigQuery format: YYYY-MM-DD HH:MM:SS."""
    if not iso_str or not isinstance(iso_str, str):
        return None
    # Strip timezone and replace T with space; keep only date and time
    m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})", iso_str.replace("Z", "+00:00"))
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return iso_str


def _int_or_none(v: Any) -> Optional[int]:
    """Coerce to int for INTEGER columns; None stays None. Avoids float for BQ."""
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema for the competitors table (flattened, one row per competitor)."""
    return [
        bigquery.SchemaField("sportradar_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("country", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("abbreviation", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("gender", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("pro_year", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("handedness", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("height", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("date_of_birth", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("generated_at", "TIMESTAMP", mode="NULLABLE"),
    ]

def payload_to_rows(raw: dict) -> list[dict]:
    """Transform raw payload to rows (one row per competitor). Returns list for extend()."""
    generated_at = raw.get("generated_at")
    competitor = raw.get("competitor") or {}
    info = raw.get("info") or {}
    return [row_to_bq(competitor, info, generated_at=generated_at)]

def row_to_bq(competitor: dict, info: dict, *, generated_at: Optional[str] = None) -> dict:
    """One raw competitor -> one flat row for BigQuery. Normalizes types for insert_rows_json."""
    return {
        "sportradar_id": competitor.get("id") if competitor.get("id") is not None else None,
        "name": competitor.get("name"),
        "country": competitor.get("country"),
        "abbreviation": competitor.get("abbreviation"),
        "gender": competitor.get("gender"),
        "pro_year": _int_or_none(info.get("pro_year")),
        "handedness": info.get("handedness"),
        "height": _int_or_none(info.get("height")),
        "date_of_birth": info.get("date_of_birth"),
        "generated_at": _timestamp_for_bq(generated_at),
    }