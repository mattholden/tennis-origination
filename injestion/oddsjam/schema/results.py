"""
OddsJam results table: BigQuery schema and transform (raw payload -> rows).

Raw API response shape (example):
{"data": [{"sport": {...}, "league": {...}, "fixture": {...}, "scores": {...}, ...}]}

We store one row per item in data. If the API returns {"data": []}, we emit a
single no_results row keyed by the requested fixture_id.
"""

import json
from typing import Any

from google.cloud import bigquery


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema for the oddsjam_results table. All nullable."""
    return [
        bigquery.SchemaField("fixture_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("fixture_numerical_id", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("game_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("start_date", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("status", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("is_live", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("season_type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("season_year", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("season_week", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("venue_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("venue_location", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("venue_neutral", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("home_team_display", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("away_team_display", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("home_competitor_ids", "STRING", mode="REPEATED"),
        bigquery.SchemaField("home_competitor_names", "STRING", mode="REPEATED"),
        bigquery.SchemaField("away_competitor_ids", "STRING", mode="REPEATED"),
        bigquery.SchemaField("away_competitor_names", "STRING", mode="REPEATED"),
        bigquery.SchemaField("sport_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("sport_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("sport_numerical_id", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("league_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("league_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("league_numerical_id", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("home_score_total", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("away_score_total", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("home_score_periods_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("away_score_periods_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("home_score_aggregate", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("away_score_aggregate", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("scores_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("in_play_period", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("in_play_period_number", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("in_play_clock", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("in_play_is_clock_stopped", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("in_play_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("events_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("stats_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("market_stats_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("sub_scores_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("extra_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("retirement_info_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("tournament_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("tournament_stage_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("last_checked_at", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("no_results", "BOOLEAN", mode="NULLABLE"),
    ]


def _int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _json_or_none(v: Any) -> str | None:
    return json.dumps(v) if v is not None else None


def _empty_data_no_results_row(fixture_id: str | None) -> dict[str, Any]:
    """Single row when API returns {'data': []}: only fixture_id and no_results=True."""
    return {
        "fixture_id": fixture_id,
        "fixture_numerical_id": None,
        "game_id": None,
        "start_date": None,
        "status": None,
        "is_live": None,
        "season_type": None,
        "season_year": None,
        "season_week": None,
        "venue_name": None,
        "venue_location": None,
        "venue_neutral": None,
        "home_team_display": None,
        "away_team_display": None,
        "home_competitor_ids": [],
        "home_competitor_names": [],
        "away_competitor_ids": [],
        "away_competitor_names": [],
        "sport_id": None,
        "sport_name": None,
        "sport_numerical_id": None,
        "league_id": None,
        "league_name": None,
        "league_numerical_id": None,
        "home_score_total": None,
        "away_score_total": None,
        "home_score_periods_json": None,
        "away_score_periods_json": None,
        "home_score_aggregate": None,
        "away_score_aggregate": None,
        "scores_json": None,
        "in_play_period": None,
        "in_play_period_number": None,
        "in_play_clock": None,
        "in_play_is_clock_stopped": None,
        "in_play_json": None,
        "events_json": None,
        "stats_json": None,
        "market_stats_json": None,
        "sub_scores_json": None,
        "extra_json": None,
        "retirement_info_json": None,
        "tournament_json": None,
        "tournament_stage_json": None,
        "last_checked_at": None,
        "no_results": True,
    }


def _result_to_row(item: dict[str, Any], requested_fixture_id: str | None) -> dict[str, Any]:
    """Convert one result item from the API to a flat dict for BigQuery."""
    sport = item.get("sport") or {}
    league = item.get("league") or {}
    fixture = item.get("fixture") or {}
    scores = item.get("scores") or {}
    in_play = item.get("in_play") or {}
    home_score = scores.get("home") or {}
    away_score = scores.get("away") or {}
    home_competitors = fixture.get("home_competitors") or []
    away_competitors = fixture.get("away_competitors") or []

    return {
        "fixture_id": fixture.get("id") or requested_fixture_id,
        "fixture_numerical_id": _int_or_none(fixture.get("numerical_id")),
        "game_id": fixture.get("game_id"),
        "start_date": fixture.get("start_date"),
        "status": fixture.get("status"),
        "is_live": fixture.get("is_live"),
        "season_type": fixture.get("season_type"),
        "season_year": fixture.get("season_year"),
        "season_week": fixture.get("season_week"),
        "venue_name": fixture.get("venue_name"),
        "venue_location": fixture.get("venue_location"),
        "venue_neutral": fixture.get("venue_neutral"),
        "home_team_display": fixture.get("home_team_display"),
        "away_team_display": fixture.get("away_team_display"),
        "home_competitor_ids": [c.get("id") for c in home_competitors if c.get("id")],
        "home_competitor_names": [c.get("name") for c in home_competitors if c.get("name")],
        "away_competitor_ids": [c.get("id") for c in away_competitors if c.get("id")],
        "away_competitor_names": [c.get("name") for c in away_competitors if c.get("name")],
        "sport_id": sport.get("id"),
        "sport_name": sport.get("name"),
        "sport_numerical_id": _int_or_none(sport.get("numerical_id")),
        "league_id": league.get("id"),
        "league_name": league.get("name"),
        "league_numerical_id": _int_or_none(league.get("numerical_id")),
        "home_score_total": _int_or_none(home_score.get("total")),
        "away_score_total": _int_or_none(away_score.get("total")),
        "home_score_periods_json": _json_or_none(home_score.get("periods")),
        "away_score_periods_json": _json_or_none(away_score.get("periods")),
        "home_score_aggregate": (
            None if home_score.get("aggregate") is None else str(home_score.get("aggregate"))
        ),
        "away_score_aggregate": (
            None if away_score.get("aggregate") is None else str(away_score.get("aggregate"))
        ),
        "scores_json": _json_or_none(scores),
        "in_play_period": None if in_play.get("period") is None else str(in_play.get("period")),
        "in_play_period_number": (
            None if in_play.get("period_number") is None else str(in_play.get("period_number"))
        ),
        "in_play_clock": in_play.get("clock"),
        "in_play_is_clock_stopped": in_play.get("is_clock_stopped"),
        "in_play_json": _json_or_none(in_play),
        "events_json": _json_or_none(item.get("events")),
        "stats_json": _json_or_none(item.get("stats")),
        "market_stats_json": _json_or_none(item.get("market_stats")),
        "sub_scores_json": _json_or_none(item.get("sub_scores")),
        "extra_json": _json_or_none(item.get("extra")),
        "retirement_info_json": _json_or_none(item.get("retirement_info")),
        "tournament_json": _json_or_none(fixture.get("tournament")),
        "tournament_stage_json": _json_or_none(fixture.get("tournament_stage")),
        "last_checked_at": item.get("last_checked_at"),
        "no_results": False,
    }


def payload_to_rows(raw: dict, **kwargs: Any) -> list[dict]:
    """
    Transform results API response to one row per data item.
    When API returns {"data": []}, emit one row with fixture_id from kwargs and no_results=True.
    Raises ValueError if "data" key is missing.
    """
    if "data" not in raw:
        raise ValueError("Results API response missing 'data' key; cannot process.")
    data = raw.get("data") or []
    fixture_id = kwargs.get("fixture_id")
    if not data:
        return [_empty_data_no_results_row(fixture_id)]
    return [_result_to_row(item, fixture_id) for item in data]
