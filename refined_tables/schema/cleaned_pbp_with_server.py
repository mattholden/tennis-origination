"""
Refined play-by-play with event_summary merge and server competitor columns.

Matches cleaned_pbp_with_server DataFrame dtypes from the serve_stats notebook pipeline.
"""

from google.cloud import bigquery


def get_schema() -> list[bigquery.SchemaField]:
    """
    BigQuery schema for cleaned_pbp_with_server.

    Grain: one row per timeline event (multiple rows per sport_event_id).
    """
    return [
        bigquery.SchemaField("sport_event_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("timeline_not_available", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("event_id", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("event_order", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("time", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("competitor", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("period_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("period", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("home_score", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("away_score", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("server", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("result", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("first_serve_fault", "BOOLEAN", mode="NULLABLE"),
        bigquery.SchemaField("total_sets", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("mode_best_of", "INT64", mode="NULLABLE"),
        bigquery.SchemaField("home_competitor_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("away_competitor_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("home_competitor_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("away_competitor_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("match_status", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("server_competitor_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("server_competitor_id", "STRING", mode="NULLABLE"),
    ]
