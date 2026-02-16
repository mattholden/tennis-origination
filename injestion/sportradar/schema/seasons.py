"""
Seasons table: BigQuery schema and transform (raw payload -> rows).

Raw API shape:
  { "generated_at": "ISO8601", "seasons": [ {...}, ... ] }
  Each season: id, name, start_date, end_date, year, competition_id.
Only include seasons whose competition_id is in allowed_competition_ids
(ids from our competitions table in BQ: ATP, WTA, Davis Cup, BJK Cup).
"""

from typing import Optional

from google.cloud import bigquery


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema for the seasons table (flattened, one row per season)."""
    return [
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("start_date", "DATE", mode="NULLABLE"),
        bigquery.SchemaField("end_date", "DATE", mode="NULLABLE"),
        bigquery.SchemaField("year", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("competition_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("generated_at", "TIMESTAMP", mode="NULLABLE"),
    ]


def row_to_bq(
    record: dict,
    *,
    generated_at: Optional[str] = None,
) -> dict:
    """One raw season -> one flat row for BigQuery."""
    return {
        "id": record.get("id"),
        "name": record.get("name"),
        "start_date": record.get("start_date"),
        "end_date": record.get("end_date"),
        "year": record.get("year"),
        "competition_id": record.get("competition_id"),
        "generated_at": generated_at,
    }


def payload_to_rows(
    raw: dict,
    *,
    allowed_competition_ids: frozenset[str],
) -> list[dict]:
    """
    Full API response -> list of rows. Only includes seasons whose
    competition_id is in allowed_competition_ids (from the competitions table in BQ).
    """
    generated_at = raw.get("generated_at")
    seasons = raw.get("seasons") or []
    return [
        row_to_bq(r, generated_at=generated_at)
        for r in seasons
        if r.get("competition_id") in allowed_competition_ids
    ]
