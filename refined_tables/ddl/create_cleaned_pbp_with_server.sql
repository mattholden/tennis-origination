-- Replace your_project.your_dataset.cleaned_pbp_with_server with BIGQUERY_REFINED_CLEANED_PBP_WITH_SERVER_TABLE_ID.
-- Run in BigQuery console or pipe through bq query --use_legacy_sql=false

CREATE TABLE IF NOT EXISTS `your_project.your_dataset.cleaned_pbp_with_server` (
  sport_event_id STRING NOT NULL,
  timeline_not_available BOOL,
  event_id INT64,
  event_order INT64,
  type STRING,
  `time` TIMESTAMP,
  competitor STRING,
  period_name STRING,
  period FLOAT64,
  home_score INT64,
  away_score INT64,
  server STRING,
  result STRING,
  first_serve_fault BOOL,
  total_sets INT64,
  mode_best_of INT64,
  home_competitor_id STRING,
  away_competitor_id STRING,
  home_competitor_name STRING,
  away_competitor_name STRING,
  match_status STRING,
  server_competitor_name STRING,
  server_competitor_id STRING
);
