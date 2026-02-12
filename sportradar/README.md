# Sportradar API – fetch and reference schemas

This directory holds:

1. **API client** – fetch data from the Sportradar Tennis API using `SPORTRADAR_API_KEY` from `.env`.
2. **Reference table schemas** – target schemas for **competitions** and **seasons** so the data engineer can create tables and keep them updated.

## Environment

- **`SPORTRADAR_API_KEY`** (required): Your Sportradar API key. Set in the project root `.env`.
- **`SPORTRADAR_BASE_URL`** (optional): Defaults to `https://api.sportradar.com/tennis/trial/v3/en`.

## Client usage

```python
from sportradar import SportradarClient

client = SportradarClient()
data = client.get_competitions()   # full competitions payload
data = client.get_seasons()       # full seasons payload
# Or raw path:
data = client.get("some/path.json")
```

## Reference schemas (for data engineer)

- **Python (BigQuery):** `sportradar/reference_schema.py`
  - `get_competitions_table_schema()` → list of `bigquery.SchemaField`
  - `get_seasons_table_schema()` → list of `bigquery.SchemaField`
  - `competitions_row_to_bq(...)`, `seasons_row_to_bq(...)` to map API rows to flat rows.

- **SQL DDL:** `sportradar/reference/`
  - `sr_competitions.sql` – table definition for competitions (flattened).
  - `sr_seasons.sql` – table definition for seasons (flattened).

## Filtering (what to load)

1. **Competitions:** Keep only rows where `category_id` is in:
   - `sr:category:3` (ATP)
   - `sr:category:6` (WTA)
   - `sr:category:76` (Davis Cup)
   - `sr:category:74` (Billie Jean King Cup)

2. **Seasons:** Keep only seasons whose `competition_id` appears in that filtered competitions list.

Details: `bigquery/category_filter_guide.md`.

## Optional: fetch and write sample files

From project root:

```bash
uv run python -m sportradar.fetch_sample
```

This uses the client to fetch competitions and seasons and write sample JSON files (or run your own script that uses `SportradarClient`).
