"""
OddsJam fixtures pipeline: bulk import all fixtures by league (ATP, WTA).
API calls -> schema transforms -> BQ upload. Saves first page per league as sample JSON.
"""

import asyncio

import core.raw_store
from injestion.oddsjam.schema import seasons as schema_seasons


LEAGUES = ("ATP", "WTA")
# LEAGUES = ("davis_cup", "laver_cup", "united_cup", "atp_challenger")
PAGE_DELAY_SECONDS = 0.5


async def run(client, manager, bq) -> None:
    """Bulk fetch all fixture pages per league; transform via schema; write fixtures and seasons to BQ."""
    fixtures_table_id = manager.get_table_id("oddsjam_fixtures")
    seasons_table_id = manager.get_table_id("oddsjam_seasons")

    for league in LEAGUES:
        season_rows: list[dict] = []
        page = 1
        total_pages = 1

        while page <= total_pages:
            raw = await manager.get_raw_async("oddsjam_fixtures", client, league=league, page=page)
            if page == 1:
                total_pages = raw.get("total_pages", 1)
                path = core.raw_store.save_raw_to_json(
                    raw,
                    f"fixtures_{league}_page1_sample",
                    source="oddsjam",
                )
                print(f"Saved sample {league} page 1 -> {path}")

            fixture_rows = manager.raw_to_rows("oddsjam_fixtures", raw)
            if fixture_rows:
                bq.write_rows(fixtures_table_id, fixture_rows)

            season_rows.extend(manager.raw_to_rows("oddsjam_seasons", raw))
            print(f"  {league} page {page}/{total_pages} -> {len(fixture_rows)} fixtures")

            page += 1
            if page <= total_pages:
                await asyncio.sleep(PAGE_DELAY_SECONDS)

        deduped_seasons = schema_seasons.dedupe_season_rows(season_rows)
        if deduped_seasons:
            bq.write_rows(seasons_table_id, deduped_seasons)
            print(f"  {league} -> {len(deduped_seasons)} unique seasons")

    print("Done.")
