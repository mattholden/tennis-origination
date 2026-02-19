"""
Sportradar manager: single entry point for schema, table_id, fetch, and load_resource.
"""

import asyncio

from injestion.sportradar import config
from injestion.sportradar.fetch import competitions as fetch_competitions
from injestion.sportradar.schema import competitions as schema_competitions
from injestion.sportradar.schema import seasons as schema_seasons
from injestion.sportradar.fetch import seasons as fetch_seasons
from injestion.sportradar.fetch import season_competitors as fetch_season_competitors
from injestion.sportradar.schema import season_competitors as schema_season_competitors
from injestion.sportradar.schema import competitors as schema_competitors
from injestion.sportradar.fetch import competitors as fetch_competitors
from injestion.sportradar.schema import surface_stats as schema_surface_stats
from injestion.sportradar.fetch import season_brackets as fetch_season_brackets
from injestion.sportradar.schema import season_brackets as schema_season_brackets
from injestion.sportradar.fetch import event_summary as fetch_event_summary
from injestion.sportradar.schema import event_summary as schema_event_summary
from injestion.sportradar.schema import event_statistics as schema_event_statistics
from injestion.sportradar.schema import event_timeline as schema_event_timeline

_REGISTRY = {
    "competitions": {
        "fetch": fetch_competitions.fetch_competitions,
        "payload_to_rows": schema_competitions.payload_to_rows,
        "get_schema": schema_competitions.get_schema,
    },
    "seasons": {
        "fetch": fetch_seasons.fetch_seasons,
        "payload_to_rows": schema_seasons.payload_to_rows,
        "get_schema": schema_seasons.get_schema,    
    },
    "season_competitors": {
        "fetch": fetch_season_competitors.fetch_season_competitors,
        "payload_to_rows": schema_season_competitors.payload_to_rows,
        "get_schema": schema_season_competitors.get_schema,
    },
    "competitors": {
        "fetch": fetch_competitors.fetch_competitors,
        "payload_to_rows": schema_competitors.payload_to_rows,
        "get_schema": schema_competitors.get_schema,
    },
    "surface_stats": {
        "payload_to_rows": schema_surface_stats.payload_to_rows,
        "get_schema": schema_surface_stats.get_schema,
    },
    "season_brackets": {
        "fetch": fetch_season_brackets.fetch_season_brackets,
        "payload_to_rows": schema_season_brackets.payload_to_rows,
        "get_schema": schema_season_brackets.get_schema,
    },
    "event_summary": {
        "fetch": fetch_event_summary.fetch_event_summary,
        "payload_to_rows": schema_event_summary.payload_to_rows,
        "get_schema": schema_event_summary.get_schema,
    },
    "event_statistics": {
        "payload_to_rows": schema_event_statistics.payload_to_rows,
        "get_schema": schema_event_statistics.get_schema,
    },
    "event_timeline": {
        "payload_to_rows": schema_event_timeline.payload_to_rows,
        "get_schema": schema_event_timeline.get_schema,
    },
}


class SportradarManager:
    """
    Single entry point for Sportradar data: schema, table_id, and load_resource.
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

    def get_raw(self, name: str, client, **kwargs) -> dict:
        """
        Fetch from API and return raw payload (sync). Use for sync pipelines.
        """
        self._check(name)
        fetch_fn = _REGISTRY[name]["fetch"]
        return fetch_fn(client, **kwargs)

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
