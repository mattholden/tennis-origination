"""
Event timeline table: BigQuery schema and transform (raw payload -> rows).

Raw API: sport_event_timeline response for one match.
  When coverage includes play_by_play: timeline[] with events { id, type, time, ... }; one row per event, timeline_not_available = false.
  When minimal coverage: no timeline; we emit one row with sport_event_id, timeline_not_available = true, all else null.
One row per timeline event (or one placeholder row when timeline not available). Only id, type, and time are present on every real event.
"""

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
    """BigQuery schema: one row per timeline event; id/type/time universal, rest nullable."""
    return [
        bigquery.SchemaField("sport_event_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("timeline_not_available", "BOOLEAN", mode="NULLABLE"),  # true when no timeline was returned
        bigquery.SchemaField("event_id", "INTEGER", mode="NULLABLE"),  # timeline item id from API
        bigquery.SchemaField("event_order", "INTEGER", mode="NULLABLE"),  # index in timeline array
        bigquery.SchemaField("type", "STRING", mode="NULLABLE"),  # point | period_start | period_score | etc.
        bigquery.SchemaField("time", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("competitor", "STRING", mode="NULLABLE"),  # home | away
        bigquery.SchemaField("period_name", "STRING", mode="NULLABLE"),  # 1st_set, etc. (period_start)
        bigquery.SchemaField("period", "STRING", mode="NULLABLE"),  # 1, 2, ... (period_score)
        bigquery.SchemaField("home_score", "INTEGER", mode="NULLABLE"),  # point or game score
        bigquery.SchemaField("away_score", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("server", "STRING", mode="NULLABLE"),  # home | away
        bigquery.SchemaField("result", "STRING", mode="NULLABLE"),  # server_won | receiver_won | ace | double_fault
        bigquery.SchemaField("first_serve_fault", "BOOLEAN", mode="NULLABLE"),
    ]


def _null_timeline_row(sport_event_id: str) -> dict:
    """Single placeholder row when timeline is missing or empty."""
    return {
        "sport_event_id": sport_event_id,
        "timeline_not_available": True,
        "event_id": None,
        "event_order": None,
        "type": None,
        "time": None,
        "competitor": None,
        "period_name": None,
        "period": None,
        "home_score": None,
        "away_score": None,
        "server": None,
        "result": None,
        "first_serve_fault": None,
    }


def payload_to_rows(raw: dict, *, sport_event_id: str) -> list[dict]:
    """
    Convert one match's sport_event_timeline payload to timeline rows.
    When timeline exists: one row per event with timeline_not_available = false.
    When timeline is missing or empty: one row with sport_event_id, timeline_not_available = true, all else null.
    """
    timeline = raw.get("timeline") or []
    if not timeline:
        return [_null_timeline_row(sport_event_id)]

    rows = []
    for idx, evt in enumerate(timeline):
        row = {
            "sport_event_id": sport_event_id,
            "timeline_not_available": False,
            "event_id": _int_or_none(evt.get("id")),
            "event_order": idx,
            "type": evt.get("type"),
            "time": evt.get("time"),
            "competitor": evt.get("competitor"),
            "period_name": evt.get("period_name"),
            "period": str(evt["period"]) if evt.get("period") is not None else None,
            "home_score": _int_or_none(evt.get("home_score")),
            "away_score": _int_or_none(evt.get("away_score")),
            "server": evt.get("server"),
            "result": evt.get("result"),
            "first_serve_fault": evt.get("first_serve_fault"),
        }
        rows.append(row)
    return rows
