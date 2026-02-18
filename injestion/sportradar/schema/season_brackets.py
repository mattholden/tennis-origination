"""
Season bracket rounds table: BigQuery schema and transform (raw payload -> rows).

Raw API shape (per season):
  No bracket: { "generated_at": "ISO8601" }
  With bracket: { "generated_at": "ISO8601", "stages": [ { "order", "type", "phase", "start_date", "end_date", "year", "groups": [ { "id", "group_name", "cup_rounds": [ { "id", "name", "order", "linked_cup_rounds": [ { "id", "type": "parent" } ] } ] } ] } ] }

Flattened: one row per cup_round (or one row per season when no stages). Each round has
sport_event_id (the match for that round); parent_cup_round_id gives the hierarchy.
_sport_event_id() enforces that each cup_round has 0 or 1 sport_event.
"""

import re
from typing import Any, Optional

from google.cloud import bigquery


def _int_or_none(v: Any) -> Optional[int]:
    """Coerce to int for INTEGER columns; None stays None."""
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema: one row per round (cup_round), or one row per season when no bracket."""
    return [
        bigquery.SchemaField("season_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("generated_at", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("stage_order", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("stage_phase", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("stage_type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("stage_start_date", "DATE", mode="NULLABLE"),
        bigquery.SchemaField("stage_end_date", "DATE", mode="NULLABLE"),
        bigquery.SchemaField("stage_year", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("group_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("group_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("cup_round_id", "STRING", mode="NULLABLE"),  # NULL when no bracket
        bigquery.SchemaField("sport_event_id", "STRING", mode="NULLABLE"),  # match for this round
        bigquery.SchemaField("round_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("round_order", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("parent_cup_round_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("state", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("winner_id", "STRING", mode="NULLABLE"),
    ]


def _parent_round_id(linked: list[dict]) -> Optional[str]:
    """First linked_cup_round with type 'parent', or None."""
    for item in linked or []:
        if item.get("type") == "parent":
            return item.get("id")
    return None


def _sport_event_id(cup_round: dict) -> Optional[str]:
    """
    Return the single sport_event id for this cup_round, or None if none.
    Raises ValueError if more than one sport_event is listed (invalid API response).
    """
    events = cup_round.get("sport_events") or []
    if len(events) > 1:
        raise ValueError(
            f"Cup round {cup_round.get('id')!r} has {len(events)} sport_events; expected 0 or 1"
        )
    if not events:
        return None
    return events[0].get("id")


def payload_to_rows(raw: dict, *, season_id: str) -> list[dict]:
    """
    Convert one season's raw bracket payload to rows.
    No stages -> one row with season_id, generated_at, rest NULL.
    With stages -> one row per cup_round with parent_cup_round_id for hierarchy.
    """
    generated_at = raw.get("generated_at")
    stages = raw.get("stages") or []

    if not stages:
        return [
            {
                "season_id": season_id,
                "generated_at": generated_at,
                "stage_order": None,
                "stage_phase": None,
                "stage_type": None,
                "stage_start_date": None,
                "stage_end_date": None,
                "stage_year": None,
                "group_id": None,
                "group_name": None,
                "cup_round_id": None,
                "sport_event_id": None,
                "round_name": None,
                "round_order": None,
                "parent_cup_round_id": None,
                "state": None,
                "winner_id": None,
            }
        ]

    rows = []
    for stage in stages:
        stage_order = _int_or_none(stage.get("order"))
        stage_phase = stage.get("phase")
        stage_type = stage.get("type")
        stage_start = stage.get("start_date")  # YYYY-MM-DD for DATE
        stage_end = stage.get("end_date")
        stage_year = stage.get("year")
        for group in stage.get("groups") or []:
            group_id = group.get("id")
            group_name = group.get("group_name")
            for cup_round in group.get("cup_rounds") or []:
                linked = cup_round.get("linked_cup_rounds") or []
                parent_id = _parent_round_id(linked)
                sport_evt_id = _sport_event_id(cup_round)
                rows.append({
                    "season_id": season_id,
                    "generated_at": generated_at,
                    "stage_order": stage_order,
                    "stage_phase": stage_phase,
                    "stage_type": stage_type,
                    "stage_start_date": stage_start,
                    "stage_end_date": stage_end,
                    "stage_year": stage_year,
                    "group_id": group_id,
                    "group_name": group_name,
                    "cup_round_id": cup_round.get("id"),
                    "sport_event_id": sport_evt_id,
                    "round_name": cup_round.get("name"),
                    "round_order": _int_or_none(cup_round.get("order")),
                    "parent_cup_round_id": parent_id,
                    "state": cup_round.get("state"),
                    "winner_id": cup_round.get("winner_id"),
                })
    return rows
