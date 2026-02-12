"""
Reference table schemas for Sportradar tennis data.

For use by the data engineer: these define the target shape of tables populated
from Sportradar API responses (competitions, seasons). Filter competitions by
category_id IN (sr:category:3, sr:category:6, sr:category:76, sr:category:74)
then filter seasons by those competition_ids. See bigquery/category_filter_guide.md.
"""

from google.cloud import bigquery


# --- Competitions (from sr_competitions.json / competitions.json) -----------------

def get_competitions_table_schema() -> list[bigquery.SchemaField]:
    """
    Schema for the Sportradar competitions table (flattened).
    One row per competition. category is flattened to category_id, category_name.
    """
    return [
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("gender", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("category_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("category_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("level", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("parent_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("generated_at", "TIMESTAMP", mode="NULLABLE"),
    ]


def competitions_row_to_bq(competition: dict, generated_at: str | None = None) -> dict:
    """Convert one competition from API response to a flat row for BigQuery."""
    category = competition.get("category") or {}
    return {
        "id": competition.get("id"),
        "name": competition.get("name"),
        "type": competition.get("type"),
        "gender": competition.get("gender"),
        "category_id": category.get("id"),
        "category_name": category.get("name"),
        "level": competition.get("level"),
        "parent_id": competition.get("parent_id"),
        "generated_at": generated_at,
    }


# --- Seasons (from sr_seasons.json / seasons.json) -------------------------------

def get_seasons_table_schema() -> list[bigquery.SchemaField]:
    """
    Schema for the Sportradar seasons table (flattened).
    One row per season. Filter by competition_id from filtered competitions table.
    """
    return [
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("start_date", "DATE", mode="NULLABLE"),
        bigquery.SchemaField("end_date", "DATE", mode="NULLABLE"),
        bigquery.SchemaField("year", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("competition_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("generated_at", "TIMESTAMP", mode="NULLABLE"),
    ]


def seasons_row_to_bq(season: dict, generated_at: str | None = None) -> dict:
    """Convert one season from API response to a flat row for BigQuery."""
    return {
        "id": season.get("id"),
        "name": season.get("name"),
        "start_date": season.get("start_date"),
        "end_date": season.get("end_date"),
        "year": season.get("year"),
        "competition_id": season.get("competition_id"),
        "generated_at": generated_at,
    }
