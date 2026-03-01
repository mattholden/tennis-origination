"""
Minimal BigQuery interface for pipelines: write_rows and get_param_list.

Pipelines use this to upload data and to read parameter lists (e.g. season_ids
from the seasons table) for parameterized resources. Credentials via
GOOGLE_APPLICATION_CREDENTIALS or Application Default Credentials.
"""

import os
from typing import Any

from google.cloud import bigquery


def get_client() -> bigquery.Client:
    """Return a BigQuery client. Uses GOOGLE_APPLICATION_CREDENTIALS if set."""
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
    return bigquery.Client()


def write_rows(table_id: str, rows: list[dict[str, Any]]) -> int:
    """Stream insert rows into the given table. Returns number of rows. Raises on any insert error."""
    if not rows:
        return 0
    client = get_client()
    errors = client.insert_rows_json(table_id, rows)
    if errors:
        sample = errors[:3] if len(errors) > 3 else errors
        raise RuntimeError(
            f"BigQuery insert_rows_json failed (table={table_id}, {len(errors)} errors): {sample}"
        )
    return len(rows)


def get_param_list(table_id: str, column: str) -> list[Any]:
    """
    Query the table for distinct values of one column. Use for parameterized
    pipelines (e.g. season_id from seasons table).
    Returns list of non-null values; order not guaranteed.
    """
    client = get_client()
    # Table id is project.dataset.table; quote for safe SQL
    sql = f'SELECT DISTINCT `{column}` FROM `{table_id}`'
    job = client.query(sql)
    return [row[column] for row in job.result() if row[column] is not None]


def get_competition_ids_from_competitions_table(competitions_table_id: str) -> frozenset[str]:
    """
    Return the set of competition ids stored in the competitions table.
    Used by the seasons pipeline to filter seasons to only those whose
    competition_id exists in our competitions table (ATP, WTA, Davis Cup, BJK Cup).
    """
    client = get_client()
    sql = f'SELECT DISTINCT id FROM `{competitions_table_id}`'
    job = client.query(sql)
    return frozenset(row["id"] for row in job.result() if row["id"] is not None)

def get_seasons_from_seasons_table(seasons_table_id: str) -> frozenset[str]:
    """
    Return the set of season ids stored in the seasons table.
    """
    client = get_client()
    sql = f'SELECT DISTINCT id FROM `{seasons_table_id}`'
    job = client.query(sql)
    return frozenset(row["id"] for row in job.result() if row["id"] is not None)

def get_major_competition_ids() -> frozenset[str]:
    """
    Return the set of competition ids for the major tournaments (Grand Slams, ATP Finals, WTA Finals, Davis Cup, BJK Cup).
    Used by the seasons pipeline to filter seasons to only those whose
    competition_id exists in our competitions table (ATP, WTA, Davis Cup, BJK Cup).
    """
    return frozenset({
        "sr:competition:2567", # Australian Open men's singles
        "sr:competition:2579", # French Open men's singles
        "sr:competition:2555", # Wimbledon men's singles
        "sr:competition:2591", # US Open men's singles
        "sr:competition:2571", # Australian Open women's singles
        "sr:competition:2583", # French Open women's singles
        "sr:competition:2559", # Wimbledon women's singles
        "sr:competition:2595", # US Open women's singles
    })

def get_season_ids_for_major_competitions(seasons_table_id: str) -> list[str]:
    """
    Return the list of season ids for the major tournaments (Grand Slams only for now).
    Used by the season competitors pipeline to fetch competitors for a test subset.
    """
    major_ids = get_major_competition_ids()
    major_ids_list = ", ".join(repr(cid) for cid in major_ids)  # e.g. 'sr:competition:2567', ...
    client = get_client()
    sql = f"SELECT DISTINCT id FROM `{seasons_table_id}` WHERE competition_id IN ({major_ids_list})"
    job = client.query(sql)
    return [row["id"] for row in job.result() if row["id"] is not None]

def get_competitor_ids_from_season_competitors_table(season_competitors_table_id: str) -> list[str]:
    """
    Return the list of competitor ids stored in the season competitors table.
    Used by the competitors pipeline to fetch competitors for a test subset.
    """
    client = get_client()
    sql = f'SELECT DISTINCT competitor_id FROM `{season_competitors_table_id}`'
    job = client.query(sql)
    return [row["competitor_id"] for row in job.result() if row["competitor_id"] is not None]

def get_sport_event_ids_from_season_brackets_table(season_brackets_table_id: str) -> list[str]:
    """
    Return the list of sport event ids stored in the season brackets table.
    Used by the event summaries pipeline to fetch summaries for a test subset.
    """
    client = get_client()
    sql = f'SELECT DISTINCT sport_event_id FROM `{season_brackets_table_id}`'
    job = client.query(sql)
    return [row["sport_event_id"] for row in job.result() if row["sport_event_id"] is not None]


def get_fixture_ids_from_oddsjam_fixtures_table(fixtures_table_id: str) -> list[str]:
    """
    Return the list of fixture ids from the OddsJam fixtures table.
    Used by the odds pipeline to fetch odds for all fixtures in parallel.
    """
    client = get_client()
    sql = f'SELECT DISTINCT id FROM `{fixtures_table_id}`'
    job = client.query(sql)
    return [row["id"] for row in job.result() if row["id"] is not None]

def get_existing_season_ids_from_season_brackets_table(season_brackets_table_id: str) -> list[str]:
    """
    Return the list of season ids from the season brackets table.
    Used by the season_brackets pipeline to skip already-fetched seasons.
    """
    client = get_client()
    sql = f'SELECT DISTINCT season_id FROM `{season_brackets_table_id}`'
    job = client.query(sql)
    return [row["season_id"] for row in job.result() if row["season_id"] is not None]

def get_existing_sport_event_ids_from_event_summary_table(event_summary_table_id: str) -> list[str]:
    """
    Return the list of sport event ids from the event summary table.
    Used by the event summaries pipeline to skip already-fetched sport events.
    """
    client = get_client()
    sql = f'SELECT DISTINCT sport_event_id FROM `{event_summary_table_id}`'
    job = client.query(sql)
    return [row["sport_event_id"] for row in job.result() if row["sport_event_id"] is not None]
