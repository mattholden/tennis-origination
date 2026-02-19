"""
Rankings table: BigQuery schema and transform (raw payload -> rows).

Raw API: rankings.json returns one response with generated_at and rankings[].
  Each element of rankings[]: type_id, name (ATP|WTA), year, week, gender, competitor_rankings[].
  Each competitor_ranking: rank, movement, points, competitions_played, competitor { id, name, country, country_code?, abbreviation }.
Flattened: one row per player per ranking list (ATP and WTA). generated_at is the snapshot time (when rankings were produced).
"""

import re
from typing import Any, Optional

from google.cloud import bigquery


def _int_or_none(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema: one row per player per ranking list (ATP/WTA); generated_at = when snapshot was produced."""
    return [
        bigquery.SchemaField("generated_at", "TIMESTAMP", mode="NULLABLE"),  # when this ranking snapshot was generated
        bigquery.SchemaField("ranking_name", "STRING", mode="NULLABLE"),  # ATP | WTA
        bigquery.SchemaField("gender", "STRING", mode="NULLABLE"),  # men | women
        bigquery.SchemaField("year", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("week", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("competitor_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("rank", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("movement", "INTEGER", mode="NULLABLE"),  # change from previous week
        bigquery.SchemaField("points", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("competitions_played", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("competitor_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("country", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("country_code", "STRING", mode="NULLABLE"),  # optional, e.g. missing for Neutral
        bigquery.SchemaField("abbreviation", "STRING", mode="NULLABLE"),
    ]


def payload_to_rows(raw: dict) -> list[dict]:
    """
    Convert rankings API payload to rows. One row per player per ranking list (ATP and WTA).
    generated_at on every row indicates when this snapshot was produced (for weekly updates).
    """
    generated_at = raw.get("generated_at")
    ranking_groups = raw.get("rankings") or []
    rows = []
    for group in ranking_groups:
        name = group.get("name")
        gender = group.get("gender")
        year = _int_or_none(group.get("year"))
        week = _int_or_none(group.get("week"))
        for cr in group.get("competitor_rankings") or []:
            comp = cr.get("competitor") or {}
            rows.append({
                "generated_at": generated_at,
                "ranking_name": name,
                "gender": gender,
                "year": year,
                "week": week,
                "competitor_id": comp.get("id"),
                "rank": _int_or_none(cr.get("rank")),
                "movement": _int_or_none(cr.get("movement")),
                "points": _int_or_none(cr.get("points")),
                "competitions_played": _int_or_none(cr.get("competitions_played")),
                "competitor_name": comp.get("name"),
                "country": comp.get("country"),
                "country_code": comp.get("country_code"),
                "abbreviation": comp.get("abbreviation"),
            })
    return rows
