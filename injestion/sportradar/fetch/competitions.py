"""
Competitions resource: API endpoint and fetch.
"""

ENDPOINT_PATH = "competitions.json"


def fetch_competitions(client) -> dict:
    """
    Fetch competitions from the Sportradar API.
    Returns full response: {"generated_at": "...", "competitions": [...]}.
    """
    return client.get(ENDPOINT_PATH)
