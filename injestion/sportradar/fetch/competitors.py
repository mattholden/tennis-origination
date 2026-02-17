"""
Competitors resource: API endpoint and fetch.
"""

ENDPOINT_PATH = "competitors/{competitor_id}/profile.json"


async def fetch_competitors(client, *, competitor_id: str) -> dict:
    """
    Fetch competitors from the Sportradar API.
    Returns full response: {"generated_at": "...", "competitor": {...}}.
    """
    return await client.get_async(ENDPOINT_PATH, competitor_id=competitor_id)