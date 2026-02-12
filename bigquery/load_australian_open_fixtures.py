"""
Load australian_open_fixtures.json and write rows to the BigQuery fixtures table.
Set BIGQUERY_FIXTURES_TABLE_ID in .env.

Run from project root:
  uv run python -m bigquery.load_australian_open_fixtures
  uv run python -m bigquery.load_australian_open_fixtures --input path/to/fixtures.json
"""

import argparse
import json
from pathlib import Path

from bigquery.client import get_fixtures_table_id, write_rows
from bigquery.schema import fixture_row_to_bq


def load_fixtures_json(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Australian Open fixtures into BigQuery")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "australian_open_fixtures.json",
        help="Path to australian_open_fixtures.json",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Rows per streaming insert batch (default: 500)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input file not found: {args.input}")

    rows_raw = load_fixtures_json(args.input)
    rows_bq = [fixture_row_to_bq(r) for r in rows_raw]

    table_id = get_fixtures_table_id()
    total = 0
    for i in range(0, len(rows_bq), args.batch_size):
        batch = rows_bq[i : i + args.batch_size]
        write_rows(batch, table_id=table_id)
        total += len(batch)

    print(f"Loaded {total} fixture rows into BigQuery ({table_id}).")


if __name__ == "__main__":
    main()
