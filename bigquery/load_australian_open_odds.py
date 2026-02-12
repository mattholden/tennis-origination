"""
Load australian_open_odds.json and write rows to the BigQuery table.
Configure BIGQUERY_TABLE_ID (and optionally GOOGLE_APPLICATION_CREDENTIALS) in .env.

Run from project root:
  uv run python -m bigquery.load_australian_open_odds
  # or with explicit path to JSON:
  uv run python -m bigquery.load_australian_open_odds --input path/to/odds.json
"""

import argparse
import json
from pathlib import Path

from bigquery.client import write_rows
from bigquery.schema import odds_row_to_bq


def load_odds_json(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Australian Open odds into BigQuery")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "australian_open_odds.json",
        help="Path to australian_open_odds.json",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10_000,
        help="Rows per streaming insert batch (default: 10000)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input file not found: {args.input}")

    rows_raw = load_odds_json(args.input)
    rows_bq = [odds_row_to_bq(r) for r in rows_raw]

    total = 0
    for i in range(0, len(rows_bq), args.batch_size):
        batch = rows_bq[i : i + args.batch_size]
        write_rows(batch)
        total += len(batch)

    print(f"Loaded {total} odds rows into BigQuery.")


if __name__ == "__main__":
    main()
