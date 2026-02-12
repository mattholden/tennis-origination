"""
Create the tennis OddsJam odds table if it does not exist.
Use this to bootstrap the table before loading, or to ensure the table exists.

  uv run python -m bigquery.create_table
"""

from bigquery.client import create_table_if_not_exists, get_table_id


def main() -> None:
    table_id = get_table_id()
    created = create_table_if_not_exists()
    if created:
        print(f"Created table: {table_id}")
    else:
        print(f"Table already exists: {table_id}")


if __name__ == "__main__":
    main()
