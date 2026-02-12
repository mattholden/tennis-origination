"""
Minimal Sportradar Tennis API client.

Uses SPORTRADAR_API_KEY from .env. Optional: SPORTRADAR_BASE_URL (defaults to trial v3).
"""

import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json

# Load .env from project root when this module is used
def _load_dotenv() -> None:
    try:
        import dotenv
        root = Path(__file__).resolve().parent.parent
        dotenv.load_dotenv(root / ".env")
    except ImportError:
        pass


def get_api_key() -> str:
    """Return Sportradar API key from environment. Raises if missing."""
    _load_dotenv()
    key = os.environ.get("SPORTRADAR_API_KEY")
    if not key:
        raise ValueError(
            "SPORTRADAR_API_KEY not set. Add it to .env in the project root."
        )
    return key.strip()


def get_base_url() -> str:
    """Base URL for Sportradar Tennis API (trial v3 by default)."""
    _load_dotenv()
    return os.environ.get(
        "SPORTRADAR_BASE_URL",
        "https://api.sportradar.com/tennis/trial/v3/en",
    ).rstrip("/")


class SportradarClient:
    """
    Client for Sportradar Tennis API.
    All GET responses are expected to be JSON.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
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
        Path is relative to base_url; api_key is appended.
        """
        url = self._url(path)
        req = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            raise RuntimeError(f"Sportradar API HTTP error: {e.code} {e.reason}") from e
        except URLError as e:
            raise RuntimeError(f"Sportradar API request failed: {e.reason}") from e

    def get_competitions(self) -> dict:
        """Fetch all competitions (full payload)."""
        return self.get("competitions.json")

    def get_seasons(self) -> dict:
        """Fetch all seasons (full payload)."""
        return self.get("seasons.json")
