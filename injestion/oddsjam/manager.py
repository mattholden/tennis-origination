"""
OddsJam manager: single entry point for schema, table_id, fetch, and load_resource.
"""

from injestion.oddsjam import config
from injestion.oddsjam.fetch import odds as fetch_oddsjam_odds
from injestion.oddsjam.schema import odds as schema_oddsjam_odds  
from injestion.oddsjam.fetch import results as fetch_oddsjam_results
from injestion.oddsjam.schema import results as schema_oddsjam_results
from injestion.oddsjam.fetch import fixtures as fetch_oddsjam_fixtures
from injestion.oddsjam.schema import fixtures as schema_oddsjam_fixtures
from injestion.oddsjam.schema import seasons as schema_oddsjam_seasons
import asyncio

_REGISTRY = {
    "oddsjam_odds": {
        "fetch": fetch_oddsjam_odds.fetch_odds,
        "payload_to_rows": schema_oddsjam_odds.payload_to_rows,
        "get_schema": schema_oddsjam_odds.get_schema,
    },
    "oddsjam_results": {
        "fetch": fetch_oddsjam_results.fetch_results,
        "payload_to_rows": schema_oddsjam_results.payload_to_rows,
        "get_schema": schema_oddsjam_results.get_schema,
    },
    "oddsjam_fixtures": {
        "fetch": fetch_oddsjam_fixtures.fetch_fixtures_page,
        "payload_to_rows": schema_oddsjam_fixtures.payload_to_rows,
        "get_schema": schema_oddsjam_fixtures.get_schema,
    },
    "oddsjam_seasons": {
        "payload_to_rows": schema_oddsjam_seasons.payload_to_rows,
        "get_schema": schema_oddsjam_seasons.get_schema,
    },
}

class OddsJamManager:
    """
    Single entry point for OddsJam data: schema, table_id, and load_resource.
    I/O (fetch) and transform (payload_to_rows) are invoked inside load_resource.
    """

    def list_resources(self) -> list[str]:
        """Resource names this manager supports (derived from registry)."""
        return list(_REGISTRY.keys())
    
    def get_schema(self, name: str):
        """BigQuery schema for the given resource."""
        self._check(name)
        return _REGISTRY[name]["get_schema"]()

    def get_table_id(self, name: str) -> str:
        """BigQuery table ID for the given resource (from config/env)."""
        return config.get_table_id(name)

    async def get_raw_async(self, name: str, client, **kwargs) -> dict:
        """
        Fetch from API and return raw payload (async). Use for async pipelines
        so many requests can run concurrently. Resource must have an async fetch.
        """
        self._check(name)
        fetch_fn = _REGISTRY[name]["fetch"]
        result = fetch_fn(client, **kwargs)
        return await result if asyncio.iscoroutine(result) else result

    def raw_to_rows(self, name: str, raw: dict, **kwargs) -> list[dict]:
        """Transform raw payload to rows. Pass **kwargs (e.g. allowed_competition_ids) for resources that need them."""
        self._check(name)
        payload_to_rows = _REGISTRY[name]["payload_to_rows"]
        return payload_to_rows(raw, **kwargs)

    def _check(self, name: str) -> None:
        if name not in _REGISTRY:
            raise ValueError(
                f"Unknown resource: {name!r}. Known: {list(_REGISTRY.keys())}"
            )