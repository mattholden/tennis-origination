"""
OddsJam seasons table: BigQuery schema and transform derived from fixture data.

Seasons are unique (league_id, league_name, season_year, season_type) extracted
from the fixtures API. season_type is the tournament/location (e.g. "Marseille, France").
One row per distinct season. Deduplication across pages is done here.
"""

from google.cloud import bigquery


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema for the oddsjam_seasons table."""
    return [
        bigquery.SchemaField("league_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("league_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("season_year", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("season_type", "STRING", mode="NULLABLE"),
    ]


def _season_key(row: dict) -> tuple[str | None, str | None, str | None, str | None]:
    """Unique key for a season row."""
    return (
        row.get("league_id"),
        row.get("league_name"),
        row.get("season_year"),
        row.get("season_type"),
    )


def payload_to_rows(raw: dict) -> list[dict]:
    """
    Extract unique seasons from one page of fixtures.
    raw: {"data": [fixture_dict, ...], "page": N, "total_pages": N}
    Returns one row per distinct (league_id, league_name, season_year, season_type) on this page.
    """
    data = raw.get("data") or []
    seen: set[tuple[str | None, str | None, str | None, str | None]] = set()
    rows: list[dict] = []
    for fixture in data:
        league = fixture.get("league") or {}
        row = {
            "league_id": league.get("id"),
            "league_name": league.get("name"),
            "season_year": fixture.get("season_year"),
            "season_type": fixture.get("season_type"),
        }
        key = _season_key(row)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def dedupe_season_rows(rows: list[dict]) -> list[dict]:
    """
    Return unique season rows by (league_id, league_name, season_year, season_type).
    Use after collecting rows from multiple pages so the pipeline stays stateless.
    """
    seen: set[tuple[str | None, str | None, str | None, str | None]] = set()
    out: list[dict] = []
    for row in rows:
        key = _season_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out
