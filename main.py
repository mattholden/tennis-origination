import asyncio
from prizepicks_oddsjam.client import OddsJamAsyncClient
from prizepicks_oddsjam.common.enums.market import TennisMarket
from prizepicks_oddsjam.common.enums.sportsbook import Sportsbook
from prizepicks_oddsjam.config import OddsJamSettings
from prizepicks_oddsjam.odds.models.requests import OddsRequestParams

async def main():
    settings = OddsJamSettings()
    
    async with OddsJamAsyncClient(settings) as client:
        request = OddsRequestParams(
            fixture_id="20260127CF5ECA5D",  # your fixture ID
            sportsbook=[Sportsbook.DRAFTKINGS],
            market=[TennisMarket.MONEYLINE]
        )
        response = await client.get_odds(request)
        print(response)

if __name__ == "__main__":
    asyncio.run(main())