"""
Sportradar Tennis API client.

Uses SPORTRADAR_API_KEY and optional SPORTRADAR_BASE_URL from environment.
Ensure the entry point (e.g. runner) calls core.env.load_env() so .env is loaded.
"""

import json
import os
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def get_api_key() -> str:
    """Return Sportradar API key from environment. Raises if missing."""
    key = os.environ.get("SPORTRADAR_API_KEY")
    if not key:
        raise ValueError(
            "SPORTRADAR_API_KEY not set. Add it to .env in the project root."
        )
    return key.strip()


def get_base_url() -> str:
    """Base URL for Sportradar Tennis API (trial v3 by default)."""
    return os.environ.get(
        "SPORTRADAR_BASE_URL",
        "https://api.sportradar.com/tennis/trial/v3/en",
    ).rstrip("/")


class SportradarClient:
    """
    Client for Sportradar Tennis API. All GET responses are expected to be JSON.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self._api_key = (api_key or get_api_key()).strip()
        self._base_url = (base_url or get_base_url()).rstrip("/")

    def _url(self, path: str) -> str:
        path = path.lstrip("/")
        sep = "&" if "?" in path else "?"
        return f"{self._base_url}/{path}{sep}api_key={self._api_key}"

    def get(self, path: str) -> dict:
        """
        GET a path (e.g. 'competitions.json') and return parsed JSON.
        The .json suffix is the response format (Sportradar also supports .xml).
        """
        url = self._url(path)
        req = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            raise RuntimeError(
                f"Sportradar API HTTP error: {e.code} {e.reason}"
            ) from e
        except URLError as e:
            raise RuntimeError(
                f"Sportradar API request failed: {e.reason}"
            ) from e
