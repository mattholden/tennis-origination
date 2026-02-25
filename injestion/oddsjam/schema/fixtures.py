"""
OddsJam fixtures table: BigQuery schema and transform (raw payload -> rows).

Raw API response per page: {"data": [...], "page": N, "total_pages": N}.
Each item in data is a fixture dict; we flatten for BQ (sport/league/competitors/result).
"""

import json
from typing import Any

from google.cloud import bigquery


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema for the oddsjam_fixtures table."""
    return [
        bigquery.SchemaField("id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("numerical_id", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("game_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("start_date", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("home_team_display", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("away_team_display", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("status", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("is_live", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("season_type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("season_year", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("season_week", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("venue_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("venue_location", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("venue_neutral", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("sport_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("sport_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("sport_numerical_id", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("league_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("league_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("league_numerical_id", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("has_odds", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("home_competitor_ids", "STRING", mode="REPEATED"),
        bigquery.SchemaField("home_competitor_names", "STRING", mode="REPEATED"),
        bigquery.SchemaField("away_competitor_ids", "STRING", mode="REPEATED"),
        bigquery.SchemaField("away_competitor_names", "STRING", mode="REPEATED"),
        bigquery.SchemaField("home_competitors_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("away_competitors_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("result_json", "STRING", mode="NULLABLE"),
    ]


def _fixture_row_to_bq(row: dict[str, Any]) -> dict[str, Any]:
    """Convert one fixture from API data to a flat dict for BigQuery."""
    sport = row.get("sport") or {}
    league = row.get("league") or {}
    home_competitors = row.get("home_competitors") or []
    away_competitors = row.get("away_competitors") or []
    result = row.get("result") or {}
    return {
        "id": row.get("id"),
        "numerical_id": row.get("numerical_id"),
        "game_id": row.get("game_id"),
        "start_date": row.get("start_date"),
        "home_team_display": row.get("home_team_display"),
        "home_competitor_names": [c["name"] for c in home_competitors if c.get("name")],
        "home_competitor_ids": [c["id"] for c in home_competitors if c.get("id")],
        "away_team_display": row.get("away_team_display"),
        "away_competitor_names": [c["name"] for c in away_competitors if c.get("name")],
        "away_competitor_ids": [c["id"] for c in away_competitors if c.get("id")],
        "status": row.get("status"),
        "is_live": row.get("is_live"),
        "season_type": row.get("season_type"),
        "season_year": row.get("season_year"),
        "season_week": row.get("season_week"),
        "venue_name": row.get("venue_name"),
        "venue_location": row.get("venue_location"),
        "venue_neutral": row.get("venue_neutral"),
        "sport_id": sport.get("id"),
        "sport_name": sport.get("name"),
        "sport_numerical_id": sport.get("numerical_id"),
        "league_id": league.get("id"),
        "league_name": league.get("name"),
        "league_numerical_id": league.get("numerical_id"),
        "has_odds": row.get("has_odds"),
        "home_competitors_json": json.dumps(row["home_competitors"]) if row.get("home_competitors") is not None else None,
        "away_competitors_json": json.dumps(row["away_competitors"]) if row.get("away_competitors") is not None else None,
        "result_json": json.dumps(row["result"]) if row.get("result") is not None else None,
    }


def payload_to_rows(raw: dict) -> list[dict]:
    """
    Transform one page response to fixture rows.
    raw: {"data": [fixture_dict, ...], "page": N, "total_pages": N}
    """
    data = raw.get("data") or []
    return [_fixture_row_to_bq(row) for row in data]
