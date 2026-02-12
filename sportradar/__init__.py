"""
Sportradar API client and reference schemas for tennis data.

- client: fetch data from Sportradar Tennis API (SPORTRADAR_API_KEY in .env).
- reference_schema: BigQuery table schemas for competitions and seasons (reference for data engineer).
"""

from sportradar.client import SportradarClient
from sportradar.reference_schema import (
    get_competitions_table_schema,
    get_seasons_table_schema,
    competitions_row_to_bq,
    seasons_row_to_bq,
)

__all__ = [
    "SportradarClient",
    "get_competitions_table_schema",
    "get_seasons_table_schema",
    "competitions_row_to_bq",
    "seasons_row_to_bq",
]
