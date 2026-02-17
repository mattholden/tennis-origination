"""
Seasons resource: API endpoint and fetch.
"""

ENDPOINT_PATH = "seasons.json"


async def fetch_seasons(client) -> dict:
    """
    Fetch seasons from the Sportradar API.
    Returns full response: {"generated_at": "...", "seasons": [...]}.
    """
    return await client.get_async(ENDPOINT_PATH)