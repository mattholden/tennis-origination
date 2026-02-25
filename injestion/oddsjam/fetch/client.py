"""
OpticOdds API v3 client (used for OddsJam/OpticOdds data).

Uses OPTICODDS_API_KEY and optional OPTICODDS_BASE_URL from environment.
Ensure the entry point (e.g. runner) calls core.env.load_env() so .env is loaded.

All requests use GET with query parameters and x-api-key header.
Pipelines use get_async() for non-blocking requests.
"""

from typing import Any, Optional

import httpx

from injestion.oddsjam import config as oddsjam_config


class OpticOddsClient:
    """
    Client for OpticOdds API v3. All GET responses are JSON.
    Uses query parameters (not path params). Auth via x-api-key header.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self._api_key = (api_key or oddsjam_config.get_api_key()).strip()
        self._base_url = (base_url or oddsjam_config.get_base_url()).rstrip("/")
        self._headers = {"x-api-key": self._api_key, "Accept": "application/json"}

    def _url(self, path: str) -> str:
        path = path.lstrip("/")
        return f"{self._base_url}/{path}"

    def get(self, path: str, params: Optional[dict[str, Any]] = None) -> dict:
        """
        GET a path and return parsed JSON (blocking).
        path: URL path relative to base (e.g. "fixtures").
        params: Optional query parameters (dict; lists are serialized by httpx).
        """
        url = self._url(path)
        with httpx.Client(timeout=60.0) as client:
            resp = client.get(url, headers=self._headers, params=params or {})
            resp.raise_for_status()
            return resp.json()

    async def get_async(self, path: str, params: Optional[dict[str, Any]] = None) -> dict:
        """
        GET a path and return parsed JSON (non-blocking). Use from async code.
        path: URL path relative to base (e.g. "fixtures").
        params: Optional query parameters (dict; lists are serialized by httpx).
        """
        url = self._url(path)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url, headers=self._headers, params=params or {})
            resp.raise_for_status()
            return resp.json()
