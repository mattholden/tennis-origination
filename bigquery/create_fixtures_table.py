"""
Create the tennis fixtures table if it does not exist.
Requires BIGQUERY_FIXTURES_TABLE_ID in .env.

  uv run python -m bigquery.create_fixtures_table
"""

from bigquery.client import create_fixtures_table_if_not_exists, get_fixtures_table_id


def main() -> None:
    table_id = get_fixtures_table_id()
    created = create_fixtures_table_if_not_exists()
    if created:
        print(f"Created fixtures table: {table_id}")
    else:
        print(f"Fixtures table already exists: {table_id}")


if __name__ == "__main__":
    main()
