# BigQuery

This directory holds all BigQuery-related code for tennis-origination. The shared table holds **all tennis OddsJam odds** (Australian Open, other tournaments, etc.) with a single schema.

**Will the load script work if the table doesn't exist?** No — streaming insert requires an existing table. You can either create the table yourself once, or let the load script create it: it will create the table automatically on first run if it doesn't exist (the **dataset** must already exist in BigQuery).

## Setup

### 1. Authentication (choose one)

**Option A: SSO / Application Default Credentials (recommended for local dev)**

1. Install the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud`).
2. Log in (use your SSO account if your org uses it):
   ```bash
   gcloud auth login
   ```
3. Set Application Default Credentials so Python can use your login:
   ```bash
   gcloud auth application-default login
   ```
   This opens a browser to sign in; credentials are stored locally.
4. Optional: set default project:
   ```bash
   gcloud config set project YOUR_PROJECT_ID
   ```
5. Do **not** set `GOOGLE_APPLICATION_CREDENTIALS` in `.env`; the client will use these credentials.

**Option B: Service account key**

- Add to `.env`: `GOOGLE_APPLICATION_CREDENTIALS=/path/to/your-service-account.json`

### 2. Environment variables

Add to project `.env` (not committed):

```env
# Odds table (required for odds loads)
BIGQUERY_TABLE_ID=your_project.your_dataset.tennis_odds

# Fixtures table (required for fixture loads)
BIGQUERY_FIXTURES_TABLE_ID=your_project.your_dataset.tennis_fixtures

# Only if using a service account key (omit when using SSO/ADC):
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/your-service-account.json
```

### 3. Dataset and table

- **Dataset**: Create the BigQuery dataset in the console (or `bq mk dataset project_id:dataset_id`) if it doesn't exist. The load script does not create datasets.
- **Table**: Either leave it to the load script (it will create the table on first run with the correct schema), or run `uv run python -m bigquery.create_table` to create it now, or create it manually with the same schema. Current schema (defined in `bigquery/schema.py`):

   ```sql
   CREATE TABLE your_dataset.tennis_odds (
     id STRING,
     sportsbook STRING,
     market STRING,
     over_under STRING,
     is_main BOOL,
     selection STRING,
     normalized_selection STRING,
     market_id STRING,
     selection_line STRING,
     player_id STRING,
     team_id STRING,
     fixture_id STRING,
     opening_line_price FLOAT64,
     opening_line_points FLOAT64,
     closing_line_price FLOAT64,
     closing_line_points FLOAT64
   );
   ```

### 4. Install dependencies (from project root)

   ```bash
   uv sync
   ```

## Load Australian Open odds

From the **project root**:

```bash
uv run python -m bigquery.load_australian_open_odds
```

Optional:

- `--input path/to/odds.json` — path to the JSON file (default: `australian_open_odds.json` in project root).
- `--batch-size 10000` — rows per streaming insert (default: 10000).

## Load Australian Open fixtures

Set `BIGQUERY_FIXTURES_TABLE_ID` in `.env`. Create the table once (or run `uv run python -m bigquery.create_fixtures_table`), then:

```bash
uv run python -m bigquery.load_australian_open_fixtures
```

Optional: `--input path/to/fixtures.json`, `--batch-size 500`.
