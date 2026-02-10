import asyncio
import httpx
import json
from typing import Optional
from prizepicks_oddsjam.config import OddsJamSettings


class OpticOddsClient:
    """
    Direct client for OpticOdds API v3.
    Provides fixtures and odds endpoints that prizepicks-oddsjam doesn't support.
    """
    
    BASE_URL = "https://api.opticodds.com/api/v3"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"x-api-key": api_key}
        self.sport = "tennis"
        self.markets = [
            "moneyline",
            "total_games",
            "total_break_points", 
            "player_break_points_won", 
            "total_tie_breaks", 
            "total_double_faults",
            "total_aces",
            "total_sets",
            "player_sets_won",
            "player_first_serve_percentage",
            "total_breaks",
            "player_aces",
            "player_games_won",
            "player_aces_+_double_faults",
            "player_double_faults",
            "total_double_faults",
            '1st_set_total_games',
            '1st_set_player_aces',
            '1st_set_player_games_won',
            '1st_set_total_aces',
            '1st_set_total_breaks'
        ]
        self.sportsbooks = [
            #"bet365",
            #"betmgm", 
            #"betonline", 
            "betrivers", 
            "bovada", 
            #"caesars", 
            #"espn_bet", 
            "hard_rock", 
            "pinnacle", 
            #"underdog_fantasy_multipliers_", 
            "draftkings", 
            #"fanduel"
        ]
        self.season_week = [
            "round of 128",
            "round of 64",
            "round of 32",
            "round of 16",
            "quarterfinals",
            "semifinals",
            "finals",
        ]
        self.season_type = "Australian Open"
        self.league = "atp"
        self.start_date_before = "2026-02-02T00:00:00Z"
        self.start_date_after = "2026-01-11T00:00:00Z"
    
    def _odds_params(self, fixture_id: str) -> dict:
        """Build params for odds endpoints. API allows max 5 sportsbooks per request."""
        return {
            "fixture_id": fixture_id,
            "sportsbook": self.sportsbooks[:5],
            "market": self.markets,
            "is_main": True,
        }

    async def get_odds(self, fixture_id: str) -> dict:
        """
        Fetch current odds for a fixture.
        API allows max 5 sportsbooks per request.
        """
        params = self._odds_params(fixture_id)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/fixtures/odds",
                headers=self.headers,
                params=params,
            )
            if response.status_code != 200:
                body = response.text
                try:
                    body = response.json()
                except Exception:
                    pass
                raise httpx.HTTPStatusError(
                    f"API returned {response.status_code}. Response: {body}",
                    request=response.request,
                    response=response,
                )
            return response.json()

    async def get_odds_historical(self, fixture_id: str) -> dict:
        """
        Fetch historical odds for a fixture (e.g. a completed or popular game).
        Same 5-sportsbook cap as get_odds. Pass a fixture_id that has odds data.
        """
        params = self._odds_params(fixture_id)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/fixtures/odds/historical",
                headers=self.headers,
                params=params,
            )
            if response.status_code != 200:
                body = response.text
                try:
                    body = response.json()
                except Exception:
                    pass
                raise httpx.HTTPStatusError(
                    f"API returned {response.status_code}. Response: {body}",
                    request=response.request,
                    response=response,
                )
            return response.json()
    
    async def get_fixtures(
        self,
        sport: Optional[str] = None,
        league: Optional[str] = None,
        start_date_after: Optional[str] = None,  # Format: YYYY-MM-DD
        start_date_before: Optional[str] = None,
        status: Optional[str] = None,  # e.g., "scheduled", "in_progress", "completed"
        page: int = 1,
        is_live: Optional[bool] = None,
        season_type: Optional[str] = None,
        season_week: Optional[str] = None,
    ) -> dict:
        """
        Fetch fixtures with optional filters.
        
        Args:
            sport: Sport name (e.g., "tennis")
            league: League name (e.g., "atp")
            start_date_after: Only fixtures starting after this date
            start_date_before: Only fixtures starting before this date
            status: Filter by status
            page: Page number for pagination
            is_live: Filter for live fixtures only
        """
        params = {"page": page}
        
        if sport:
            params["sport"] = sport
        if league:
            params["league"] = league
        if start_date_after:
            params["start_date_after"] = start_date_after
        if start_date_before:
            params["start_date_before"] = start_date_before
        if status:
            params["status"] = status
        if is_live:
            params["is_live"] = is_live
        if season_week:
            params["season_week"] = season_week
        if season_type:
            params["season_type"] = season_type
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/fixtures",
                headers=self.headers,
                params=params,
            )
            response.raise_for_status()
            return response.json()
    
    async def get_active_fixtures(
        self,
        sport: Optional[str] = None,
        league: Optional[str] = None,
    ) -> dict:
        """Get only active (upcoming/live) fixtures."""
        params = {}
        if sport:
            params["sport"] = sport
        if league:
            params["league"] = league
            
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/fixtures/active",
                headers=self.headers,
                params=params,
            )
            response.raise_for_status()
            return response.json()
    
    async def get_all_fixtures_paginated(
        self,
        max_pages: int = 10,
        start_date_after: Optional[str] = None,
        start_date_before: Optional[str] = None,
        season_week: Optional[str] = None,
        season_type: Optional[str] = None,
        league: Optional[str] = None,
        sport: Optional[str] = None,
    ) -> list:
        """Fetch all fixtures across multiple pages."""
        all_fixtures = []
        page = 1
        
        while page <= max_pages:
            result = await self.get_fixtures(
                page=page,
                start_date_after=start_date_after,
                start_date_before=start_date_before,
                season_week=season_week,
                season_type=season_type,
                league=league,
                sport=sport,
            )
            
            fixtures = result.get("data", [])
            all_fixtures.extend(fixtures)
            
            total_pages = result.get("total_pages", 1)
            print(f"Fetched page {page}/{total_pages} ({len(fixtures)} fixtures)")
            
            if page >= total_pages:
                break
            page += 1
        
        return all_fixtures


async def main():
    settings = OddsJamSettings()
    
    # Initialize the OpticOdds client
    client = OpticOddsClient(settings.api_key)
    
    # Example 1: Get active tennis fixtures
    print("=" * 60)
    print("Fetching active tennis fixtures...")
    print("=" * 60)
    all_fixtures = []
    for season_week in client.season_week:
        fixtures = await client.get_all_fixtures_paginated(
            sport="tennis",
            league="atp",
            start_date_after="2026-01-11T00:00:00Z",
            start_date_before="2026-02-02T00:00:00Z",
            season_week=season_week,
            season_type="Australian Open",
        )

        all_fixtures.extend(fixtures)

    with open("australian_open_fixtures.json", "w") as f:
        json.dump(all_fixtures, f, indent=2)
    print("Done!")

    all_odds = []
    fixture_ids = [f["id"] for f in all_fixtures]
    for fixture_id in fixture_ids:
        response = await client.get_odds_historical(fixture_id=fixture_id)
        data = response.get("data", [])
        if not data:
            continue
        odds = data[0].get("odds", [])
        for o in odds:
            o["fixture_id"] = fixture_id
        all_odds.extend(odds)

    with open("australian_open_odds.json", "w") as f:
        json.dump(all_odds, f, indent=2)
    print("Done!")



if __name__ == "__main__":
    asyncio.run(main())