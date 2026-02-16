"""
Season competitors table: BigQuery schema and transform (raw payload -> rows).

Raw API (per season): {"generated_at": "...", "season_competitors": [{ "id", "name", "short_name", "abbreviation" }, ...]}.
season_id is not in the response; the pipeline passes it when calling raw_to_rows(..., season_id=...).
Composite unique key: (season_id, competitor_id).
"""

from typing import Optional

from google.cloud import bigquery


def get_schema() -> list[bigquery.SchemaField]:
    """
    BigQuery schema for the season_competitors table.
    One row per (season, competitor). Composite unique key: (season_id, competitor_id).
    """
    return [
        bigquery.SchemaField("season_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("competitor_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("short_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("abbreviation", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("generated_at", "TIMESTAMP", mode="NULLABLE"),
    ]


def row_to_bq(
    record: dict,
    *,
    season_id: str,
    generated_at: Optional[str] = None,
) -> dict:
    """One raw competitor object -> one flat row. season_id comes from the pipeline."""
    return {
        "season_id": season_id,
        "competitor_id": record.get("id"),
        "name": record.get("name"),
        "short_name": record.get("short_name"),
        "abbreviation": record.get("abbreviation"),
        "generated_at": generated_at,
    }


def payload_to_rows(raw: dict, *, season_id: str) -> list[dict]:
    """
    Transform one season's API response to rows. season_id must be passed by the pipeline.
    """
    generated_at = raw.get("generated_at")
    competitors = raw.get("season_competitors") or []
    return [
        row_to_bq(r, season_id=season_id, generated_at=generated_at)
        for r in competitors
    ]
