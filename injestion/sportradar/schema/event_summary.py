"""
Event summary table: BigQuery schema and transform (raw payload -> rows).

Raw API: sport_event_timeline response for one match.
  { "generated_at", "sport_event": { "id", "start_time", "sport_event_context", "coverage", "competitors", "venue", "estimated" }, "sport_event_status": { "status", "match_status", "home_score", "away_score", "winner_id", "period_scores" } }
One row per match. Match metadata only (no channels). Coverage flags included.
"""

import json
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
    """BigQuery schema: one row per match, metadata + coverage (no channels)."""
    return [
        bigquery.SchemaField("sport_event_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("generated_at", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("start_time", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("start_time_confirmed", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("sport_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("category_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("category_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("competition_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("competition_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("competition_parent_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("competition_type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("competition_gender", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("competition_level", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("season_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("season_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("stage_order", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("stage_type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("stage_phase", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("stage_start_date", "DATE", mode="NULLABLE"),
        bigquery.SchemaField("stage_end_date", "DATE", mode="NULLABLE"),
        bigquery.SchemaField("stage_year", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("round_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("round_number", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("mode_best_of", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("coverage_enhanced_stats", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("coverage_detailed_serve_outcomes", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("coverage_play_by_play", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("home_competitor_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("away_competitor_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("home_competitor_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("away_competitor_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("home_competitor_seed", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("away_competitor_seed", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("venue_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("venue_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("venue_city", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("venue_country_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("venue_country_code", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("venue_timezone", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("match_status", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("home_score", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("away_score", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("winner_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("period_scores", "STRING", mode="NULLABLE"),  # JSON array of set scores
    ]


def payload_to_rows(raw: dict, *, sport_event_id: str) -> list[dict]:
    """
    Convert one match's sport_event_timeline payload to one event summary row.
    Pipeline passes sport_event_id (can also be derived from raw["sport_event"]["id"]).
    """
    event = raw.get("sport_event") or {}
    ctx = event.get("sport_event_context") or {}
    comp = ctx.get("competition") or {}
    season = ctx.get("season") or {}
    stage = ctx.get("stage") or {}
    rnd = ctx.get("round") or {}
    mode = ctx.get("mode") or {}
    coverage = event.get("coverage") or {}
    props = coverage.get("sport_event_properties") or {}
    venue = event.get("venue") or {}
    status = raw.get("sport_event_status") or {}

    competitors = event.get("competitors") or []
    home = next((c for c in competitors if c.get("qualifier") == "home"), None)
    away = next((c for c in competitors if c.get("qualifier") == "away"), None)

    period_scores = status.get("period_scores")
    period_scores_str = json.dumps(period_scores) if period_scores is not None else None

    return [
        {
            "sport_event_id": sport_event_id,
            "generated_at": raw.get("generated_at"),
            "start_time": event.get("start_time"),
            "start_time_confirmed": event.get("start_time_confirmed"),
            "sport_id": (ctx.get("sport") or {}).get("id"),
            "category_id": (ctx.get("category") or {}).get("id"),
            "category_name": (ctx.get("category") or {}).get("name"),
            "competition_id": comp.get("id"),
            "competition_name": comp.get("name"),
            "competition_parent_id": comp.get("parent_id"),
            "competition_type": comp.get("type"),
            "competition_gender": comp.get("gender"),
            "competition_level": comp.get("level"),
            "season_id": season.get("id"),
            "season_name": season.get("name"),
            "stage_order": _int_or_none(stage.get("order")),
            "stage_type": stage.get("type"),
            "stage_phase": stage.get("phase"),
            "stage_start_date": stage.get("start_date"),
            "stage_end_date": stage.get("end_date"),
            "stage_year": stage.get("year"),
            "round_name": rnd.get("name"),
            "round_number": _int_or_none(rnd.get("number")),
            "mode_best_of": _int_or_none(mode.get("best_of")),
            "coverage_enhanced_stats": props.get("enhanced_stats"),
            "coverage_detailed_serve_outcomes": props.get("detailed_serve_outcomes"),
            "coverage_play_by_play": props.get("play_by_play"),
            "home_competitor_id": home.get("id") if home else None,
            "away_competitor_id": away.get("id") if away else None,
            "home_competitor_name": home.get("name") if home else None,
            "away_competitor_name": away.get("name") if away else None,
            "home_competitor_seed": home.get("seed") if home else None,
            "away_competitor_seed": away.get("seed") if away else None,
            "venue_id": venue.get("id"),
            "venue_name": venue.get("name"),
            "venue_city": venue.get("city_name"),
            "venue_country_name": venue.get("country_name"),
            "venue_country_code": venue.get("country_code"),
            "venue_timezone": venue.get("timezone"),
            "match_status": status.get("match_status"),
            "home_score": _int_or_none(status.get("home_score")),
            "away_score": _int_or_none(status.get("away_score")),
            "winner_id": status.get("winner_id"),
            "period_scores": period_scores_str,
        }
    ]
