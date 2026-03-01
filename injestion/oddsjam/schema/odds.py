"""
OddsJam odds table: BigQuery schema and transform (raw payload -> rows).

Raw API response: {"data": [{ "id": fixture_id, "odds": [ {...}, ... ] }, ...]}.
We store one row per odds line. Structure is consistent across markets/sportsbooks;
variance: selection_line and olv/clv points are null for moneylines, selection can be "".
All columns nullable to allow for sportsbook/market differences.
"""

from typing import Any

from google.cloud import bigquery


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema for the oddsjam_odds table. All nullable."""
    return [
        bigquery.SchemaField("fixture_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("game_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("home_competitor_names", "STRING", mode="REPEATED"),
        bigquery.SchemaField("home_competitor_ids", "STRING", mode="REPEATED"),
        bigquery.SchemaField("away_competitor_names", "STRING", mode="REPEATED"),
        bigquery.SchemaField("away_competitor_ids", "STRING", mode="REPEATED"),
        bigquery.SchemaField("status", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("is_live", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("season_type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("season_year", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("season_week", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("venue_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("venue_location", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("league_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("league_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("odds_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("sportsbook", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("market", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("market_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("selection", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("normalized_selection", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("selection_line", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("is_main", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("player_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("team_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("opening_line_price", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("opening_line_points", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("closing_line_price", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("closing_line_points", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("no_odds", "BOOLEAN", mode="NULLABLE"),
    ]


def _odds_line_to_row(odds_line: dict[str, Any], fixture_data: dict[str, Any], no_odds: bool = False) -> dict[str, Any]:
    """Convert one odds line from the API to a flat dict for BigQuery."""
    olv = odds_line.get("olv") or {}
    clv = odds_line.get("clv") or {}
    return {
        **fixture_data,
        "odds_id": odds_line.get("id"),
        "sportsbook": odds_line.get("sportsbook"),
        "market": odds_line.get("market"),
        "market_id": odds_line.get("market_id"),
        "name": odds_line.get("name"),
        "selection": odds_line.get("selection"),
        "normalized_selection": odds_line.get("normalized_selection"),
        "selection_line": odds_line.get("selection_line"),
        "is_main": odds_line.get("is_main"),
        "player_id": odds_line.get("player_id"),
        "team_id": odds_line.get("team_id"),
        "opening_line_price": _float_or_none(olv.get("price")),
        "opening_line_points": _float_or_none(olv.get("points")),
        "closing_line_price": _float_or_none(clv.get("price")),
        "closing_line_points": _float_or_none(clv.get("points")),
        "no_odds": no_odds,
    }


def _float_or_none(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _empty_data_no_odds_row(fixture_id: str | None) -> dict[str, Any]:
    """Single row when API returns {"data": []}: only fixture_id and no_odds set; all else null."""
    return {
        "fixture_id": fixture_id,
        "game_id": None,
        "home_competitor_names": [],
        "home_competitor_ids": [],
        "away_competitor_names": [],
        "away_competitor_ids": [],
        "status": None,
        "is_live": None,
        "season_type": None,
        "season_year": None,
        "season_week": None,
        "venue_name": None,
        "venue_location": None,
        "league_id": None,
        "league_name": None,
        "odds_id": None,
        "sportsbook": None,
        "market": None,
        "market_id": None,
        "name": None,
        "selection": None,
        "normalized_selection": None,
        "selection_line": None,
        "is_main": None,
        "player_id": None,
        "team_id": None,
        "opening_line_price": None,
        "opening_line_points": None,
        "closing_line_price": None,
        "closing_line_points": None,
        "no_odds": True,
    }


def _fixture_no_odds_row(fixture_data: dict[str, Any]) -> dict[str, Any]:
    """Single row for a fixture that has match info but odds: []; same fixture_data, odds fields null, no_odds=True."""
    return {
        **fixture_data,
        "odds_id": None,
        "sportsbook": None,
        "market": None,
        "market_id": None,
        "name": None,
        "selection": None,
        "normalized_selection": None,
        "selection_line": None,
        "is_main": None,
        "player_id": None,
        "team_id": None,
        "opening_line_price": None,
        "opening_line_points": None,
        "closing_line_price": None,
        "closing_line_points": None,
        "no_odds": True,
    }


def payload_to_rows(raw: dict, **kwargs: Any) -> list[dict]:
    """
    Transform odds API response to one row per odds line.
    When the API returns {"data": []}, emit one row with fixture_id from kwargs and no_odds=True.
    When a fixture in data has "odds": [], emit one row with that fixture's metadata and no_odds=True.
    raw: {"data": [{ "id": fixture_id, "odds": [ {...}, ... ] }, ...]} or {"data": []}
    Raises ValueError if "data" key is missing.
    """
    if "data" not in raw:
        raise ValueError("Odds API response missing 'data' key; cannot process.")
    data = raw.get("data") or []
    fixture_id = kwargs.get("fixture_id")
    if not data:
        # No odds for this fixture: endpoint returned empty list; we only have the requested fixture_id.
        return [_empty_data_no_odds_row(fixture_id)]
    rows: list[dict] = []
    for fixture in data:
        league = fixture.get("league") or {}
        home_competitors = fixture.get("home_competitors") or []
        away_competitors = fixture.get("away_competitors") or []
        home_competitor_names = [c.get("name") for c in home_competitors if c.get("name")]
        home_competitor_ids = [c.get("id") for c in home_competitors if c.get("id")]
        away_competitor_names = [c.get("name") for c in away_competitors if c.get("name")]
        away_competitor_ids = [c.get("id") for c in away_competitors if c.get("id")]
        fixture_data = {
            "fixture_id": fixture.get("id") or fixture_id,
            "game_id": fixture.get("game_id"),
            "home_competitor_names": home_competitor_names,
            "home_competitor_ids": home_competitor_ids,
            "away_competitor_names": away_competitor_names,
            "away_competitor_ids": away_competitor_ids,
            "status": fixture.get("status"),
            "is_live": fixture.get("is_live"),
            "season_type": fixture.get("season_type"),
            "season_year": fixture.get("season_year"),
            "season_week": fixture.get("season_week"),
            "venue_name": fixture.get("venue_name"),
            "venue_location": fixture.get("venue_location"),
            "league_id": league.get("id"),
            "league_name": league.get("name"),
        }
        odds = fixture.get("odds") or []
        if not odds:
            rows.append(_fixture_no_odds_row(fixture_data))
        else:
            for line in odds:
                rows.append(_odds_line_to_row(line, fixture_data, no_odds=False))
    return rows
