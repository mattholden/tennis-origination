-- Replace your_project.your_dataset.fixture_id_mapping with
-- BIGQUERY_REFINED_FIXTURE_ID_MAPPING_TABLE_ID.
-- Run in BigQuery console or: bq query --use_legacy_sql=false < create_fixture_id_mapping.sql

CREATE TABLE IF NOT EXISTS `your_project.your_dataset.fixture_id_mapping` (
  sport_event_id STRING NOT NULL,
  fixture_id STRING NOT NULL,
  first_event_time TIMESTAMP,
  start_date TIMESTAMP,
  time_delta_minutes FLOAT64,
  home_competitor_name STRING,
  away_competitor_name STRING,
  norm_home STRING,
  norm_away STRING,
  oj_player_a STRING,
  oj_player_b STRING,
  match_method STRING,
  updated_at TIMESTAMP
);
