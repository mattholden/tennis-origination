"""
Sportradar Tennis API client.

Uses SPORTRADAR_API_KEY and optional SPORTRADAR_BASE_URL from environment.
Ensure the entry point (e.g. injestion.runner) calls injestion.core.env.load_env() so .env is loaded.

All pipelines use get_async() for non-blocking requests (enables parallel fetches where used).
"""

import os
from typing import Optional

import httpx


def get_api_key() -> str:
    """Return Sportradar API key from environment. Raises if missing."""
    key = os.environ.get("SPORTRADAR_API_KEY")
    if not key:
        raise ValueError(
            "SPORTRADAR_API_KEY not set. Add it to .env in the project root."
        )
    return key.strip()


def get_base_url() -> str:
    """Base URL for Sportradar Tennis API."""
    base_url = os.environ.get("SPORTRADAR_BASE_URL")
    if not base_url:
        raise ValueError(
            "SPORTRADAR_BASE_URL not set. Add it to .env in the project root."
        )
    return base_url.rstrip("/")


def _build_url(base_url: str, api_key: str, path: str) -> str:
    path = path.lstrip("/")
    sep = "&" if "?" in path else "?"
    return f"{base_url}/{path}{sep}api_key={api_key}"


class SportradarClient:
    """
    Client for Sportradar Tennis API. All GET responses are JSON.
    Pipelines use get_async() for fetch; get() remains available for one-off sync use if needed.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self._api_key = (api_key or get_api_key()).strip()
        self._base_url = (base_url or get_base_url()).rstrip("/")

    def _url(self, path: str) -> str:
        return _build_url(self._base_url, self._api_key, path)

    def get(self, path: str, **path_params: str) -> dict:
        """
        GET a path and return parsed JSON (blocking).

        path: URL path relative to base. Use {param_name} placeholders for path parameters.
        path_params: Values to substitute into path.
        """
        if path_params:
            path = path.format(**path_params)
        url = self._url(path)
        with httpx.Client(timeout=60.0) as client:
            resp = client.get(url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            return resp.json()

    async def get_async(self, path: str, **path_params: str) -> dict:
        """
        GET a path and return parsed JSON (non-blocking). Use from async code.

        path: URL path relative to base. Use {param_name} placeholders for path parameters.
        path_params: Values to substitute into path.
        """
        if path_params:
            path = path.format(**path_params)
        url = self._url(path)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            return resp.json()
