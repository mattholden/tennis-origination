"""
Sportradar manager: single entry point for schema, table_id, fetch, and load_resource.
"""

from injestion.sportradar import config
from injestion.sportradar.fetch import competitions as fetch_competitions
from injestion.sportradar.schema import competitions as schema_competitions


RESOURCES = ["competitions"]

_REGISTRY = {
    "competitions": {
        "fetch": fetch_competitions.fetch_competitions,
        "payload_to_rows": schema_competitions.payload_to_rows,
        "get_schema": schema_competitions.get_schema,
    },
}


class SportradarManager:
    """
    Single entry point for Sportradar data: schema, table_id, and load_resource.
    I/O (fetch) and transform (payload_to_rows) are invoked inside load_resource.
    """

    def list_resources(self) -> list[str]:
        """Resource names this manager supports."""
        return list(RESOURCES)

    def get_schema(self, name: str):
        """BigQuery schema for the given resource."""
        self._check(name)
        return _REGISTRY[name]["get_schema"]()

    def get_table_id(self, name: str) -> str:
        """BigQuery table ID for the given resource (from config/env)."""
        return config.get_table_id(name)

    def get_raw(self, name: str, client, **kwargs) -> dict:
        """
        Fetch from API and return raw payload. Use when saving raw to JSON for review
        before defining schema, or when pipeline does fetch -> save_raw -> transform -> write.
        """
        self._check(name)
        fetch_fn = _REGISTRY[name]["fetch"]
        return fetch_fn(client, **kwargs)

    def raw_to_rows(self, name: str, raw: dict) -> list[dict]:
        """Transform raw payload to rows (same as load_resource but without fetch)."""
        self._check(name)
        payload_to_rows = _REGISTRY[name]["payload_to_rows"]
        return payload_to_rows(raw)

    def _check(self, name: str) -> None:
        if name not in _REGISTRY:
            raise ValueError(
                f"Unknown resource: {name!r}. Known: {list(_REGISTRY.keys())}"
            )
