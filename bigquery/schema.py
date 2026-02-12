"""
Flatten odds and fixture records for BigQuery.
- Odds: tennis_odds table (OLV/CLV = opening/closing line value).
- Fixtures: tennis_fixtures table (sport/league flattened; competitors/result as JSON).
"""

import json
from typing import Any

from google.cloud import bigquery


def get_odds_table_schema() -> list[bigquery.SchemaField]:
    """Schema for the shared tennis OddsJam odds table. Used for create-if-not-exists."""
    return [
        bigquery.SchemaField("id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("sportsbook", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("market", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("over_under", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("is_main", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("selection", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("normalized_selection", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("market_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("selection_line", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("player_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("team_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("fixture_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("opening_line_price", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("opening_line_points", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("closing_line_price", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("closing_line_points", "FLOAT64", mode="NULLABLE"),
    ]


def odds_row_to_bq(row: dict[str, Any]) -> dict[str, Any]:
    """
    Convert one odds record from australian_open_odds.json into a flat dict for BigQuery.
    Nested olv/clv become olv_price, olv_points, clv_price, clv_points.
    """
    olv = row.get("olv") or {}
    clv = row.get("clv") or {}
    out = {
        "id": row.get("id"),
        "sportsbook": row.get("sportsbook"),
        "market": row.get("market"),
        "over_under": row.get("name"),
        "is_main": row.get("is_main"),
        "selection": row.get("selection"),
        "normalized_selection": row.get("normalized_selection"),
        "market_id": row.get("market_id"),
        "selection_line": row.get("selection_line"),
        "player_id": row.get("player_id"),
        "team_id": row.get("team_id"),
        "fixture_id": row.get("fixture_id"),
        "opening_line_price": olv.get("price"),
        "opening_line_points": olv.get("points"),
        "closing_line_price": clv.get("price"),
        "closing_line_points": clv.get("points"),
    }
    return out


def get_fixtures_table_schema() -> list[bigquery.SchemaField]:
    """Schema for the tennis fixtures table (OddsJam fixture payload, flattened)."""
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
        bigquery.SchemaField("home_competitors_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("away_competitors_json", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("result_json", "STRING", mode="NULLABLE"),
    ]


def fixture_row_to_bq(row: dict[str, Any]) -> dict[str, Any]:
    """Convert one fixture from australian_open_fixtures.json to a flat dict for BigQuery."""
    sport = row.get("sport") or {}
    league = row.get("league") or {}
    out = {
        "id": row.get("id"),
        "numerical_id": row.get("numerical_id"),
        "game_id": row.get("game_id"),
        "start_date": row.get("start_date"),
        "home_team_display": row.get("home_team_display"),
        "away_team_display": row.get("away_team_display"),
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
    return out
