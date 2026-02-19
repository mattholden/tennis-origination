"""
Event statistics table: BigQuery schema and transform (raw payload -> rows).

Raw API: sport_event_timeline response for one match.
  When coverage includes stats: statistics.totals.competitors[] with id, qualifier, statistics { aces, ... }.
  When minimal coverage: no statistics block; we emit one row per competitor with statistics_not_available = true and NULL stats.
One row per competitor per match (2 rows per match). Wide schema: all possible stat columns (nullable).
NULL for a stat = not reported / not available; 0 = player had zero for that stat (_int_or_none preserves that).
"""

from typing import Any, Optional

from google.cloud import bigquery


# All possible stat keys: basic (all coverage with stats) + enhanced-only. Order fixed for schema/row consistency.
STAT_KEYS = [
    "aces",
    "breakpoints_won",
    "double_faults",
    "first_serve_points_won",
    "first_serve_successful",
    "games_won",
    "max_games_in_a_row",
    "max_points_in_a_row",
    "points_won",
    "points_won_from_last_10",
    "second_serve_points_won",
    "second_serve_successful",
    "service_games_won",
    "service_points_lost",
    "service_points_won",
    "tiebreaks_won",
    "total_breakpoints",
    # enhanced
    "backhand_errors",
    "backhand_unforced_errors",
    "backhand_winners",
    "drop_shot_unforced_errors",
    "drop_shot_winners",
    "forehand_errors",
    "forehand_unforced_errors",
    "forehand_winners",
    "groundstroke_errors",
    "groundstroke_unforced_errors",
    "groundstroke_winners",
    "lob_unforced_errors",
    "lob_winners",
    "overhead_stroke_errors",
    "overhead_stroke_unforced_errors",
    "overhead_stroke_winners",
    "return_errors",
    "return_winners",
    "volley_unforced_errors",
    "volley_winners",
]


def _int_or_none(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema: one row per competitor per match; identifiers + statistics_not_available + one column per stat (all nullable)."""
    fields = [
        bigquery.SchemaField("sport_event_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("competitor_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("qualifier", "STRING", mode="NULLABLE"),  # home | away
        bigquery.SchemaField("statistics_not_available", "BOOLEAN", mode="NULLABLE"),  # true when no statistics block
    ]
    for key in STAT_KEYS:
        fields.append(bigquery.SchemaField(key, "INTEGER", mode="NULLABLE"))
    return fields


def payload_to_rows(raw: dict, *, sport_event_id: str) -> list[dict]:
    """
    Convert one match's sport_event_timeline payload to event statistics rows.
    Always emits two rows (one per competitor). When statistics block is missing: statistics_not_available = true, all stat columns NULL.
    When present: statistics_not_available = false, stats filled (NULL for a key = API didn't return it; 0 = zero).
    """
    event = raw.get("sport_event") or {}
    competitors = event.get("competitors") or []
    if not competitors:
        return []

    stats_block = raw.get("statistics") or {}
    totals = stats_block.get("totals") or {}
    stats_competitors = totals.get("competitors") or []
    has_stats = bool(stats_competitors)
    stats_by_qualifier = {c.get("qualifier"): c.get("statistics") or {} for c in stats_competitors}

    rows = []
    for comp in competitors:
        cid = comp.get("id")
        qualifier = comp.get("qualifier")
        if not cid:
            continue
        stat_map = stats_by_qualifier.get(qualifier) or {} if has_stats else {}
        row = {
            "sport_event_id": sport_event_id,
            "competitor_id": cid,
            "qualifier": qualifier,
            "statistics_not_available": not has_stats,
        }
        for key in STAT_KEYS:
            row[key] = _int_or_none(stat_map.get(key)) if has_stats else None
        rows.append(row)
    return rows
