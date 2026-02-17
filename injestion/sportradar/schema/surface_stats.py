"""
Surface stats table: BigQuery schema and transform (raw payload -> rows).
"""

import re
from typing import Any, Optional

from google.cloud import bigquery


def _timestamp_for_bq(iso_str: Optional[str]) -> Optional[str]:
    """Convert ISO8601 to BigQuery TIMESTAMP format: YYYY-MM-DD HH:MM:SS."""
    if not iso_str or not isinstance(iso_str, str):
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})", iso_str.replace("Z", "+00:00"))
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return iso_str


def _int_or_none(v: Any) -> Optional[int]:
    """Coerce to int for INTEGER columns; avoids float for BigQuery insert_rows_json."""
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema for the surface stats table."""
    return [
        bigquery.SchemaField("competitor_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("year", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("surface_type", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("competitions_played", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("competitions_won", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("matches_played", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("matches_won", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("generated_at", "TIMESTAMP", mode="NULLABLE"),
    ]

def payload_to_rows(raw: dict) -> list[dict]:
    """Transform raw payload to rows. Skips rows missing required year/surface_type/competitor_id."""
    generated_at = raw.get("generated_at")
    competitor = raw.get("competitor") or {}
    competitor_id = competitor.get("id")
    name = competitor.get("name")
    periods = raw.get("periods") or []
    surface_stats = []
    if not competitor_id:  # REQUIRED; skip entire payload if missing
        return surface_stats
    for period in periods:
        year_val = _int_or_none(period.get("year"))
        if year_val is None:  # year is REQUIRED in BQ
            continue
        surfaces = period.get("surfaces") or []
        for surface in surfaces:
            surface_type = surface.get("type")
            if not surface_type:  # surface_type is REQUIRED
                continue
            statistics = surface.get("statistics") or {}
            row = row_to_bq(competitor_id, name, year_val, surface_type, statistics, generated_at=generated_at)
            surface_stats.append(row)
    return surface_stats

def row_to_bq(competitor_id: str, name: str, year: int, surface_type: str, statistics: dict, *, generated_at: Optional[str] = None) -> dict:
    """One raw surface stats object -> one flat row for BigQuery. year must be int (REQUIRED)."""
    return {
        "competitor_id": competitor_id,
        "name": name,
        "year": year,
        "surface_type": surface_type,
        "competitions_played": _int_or_none(statistics.get("competitions_played")),
        "competitions_won": _int_or_none(statistics.get("competitions_won")),
        "matches_played": _int_or_none(statistics.get("matches_played")),
        "matches_won": _int_or_none(statistics.get("matches_won")),
        "generated_at": _timestamp_for_bq(generated_at),
    }