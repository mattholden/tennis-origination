"""
Sportradar sport_event_id ↔ OddsJam fixture_id crosswalk schema.

Aligns with refined_tables/fixture_id_mapping/fixture_mapping.ipynb output
(grain: one accepted link per sport_event_id / fixture_id).
"""

from google.cloud import bigquery


def get_schema() -> list[bigquery.SchemaField]:
    """BigQuery schema for fixture ID mapping rows."""
    return [
        bigquery.SchemaField("sport_event_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("fixture_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("first_event_time", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("start_date", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("time_delta_minutes", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("home_competitor_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("away_competitor_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("norm_home", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("norm_away", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("oj_player_a", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("oj_player_b", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("match_method", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="NULLABLE"),
    ]
