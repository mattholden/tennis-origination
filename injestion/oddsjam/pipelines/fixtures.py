"""
OddsJam fixtures pipeline: bulk import all fixtures by league (ATP, WTA).
API calls -> schema transforms -> BQ upload. Saves first page per league as sample JSON.
"""

import asyncio

import injestion.core.raw_store
from injestion.oddsjam.schema import seasons as schema_seasons


LEAGUES = ("ATP", "WTA")
# LEAGUES = ("davis_cup", "laver_cup", "united_cup", "atp_challenger")
PAGE_DELAY_SECONDS = 0.5


async def run(client, manager, bq) -> None:
    """Bulk fetch fixture pages per league until has_more is false; transform via schema; write fixtures and seasons to BQ."""
    fixtures_table_id = manager.get_table_id("oddsjam_fixtures")
    seasons_table_id = manager.get_table_id("oddsjam_seasons")

    for league in LEAGUES:
        season_rows: list[dict] = []
        page = 1

        while True:
            raw = await manager.get_raw_async("oddsjam_fixtures", client, league=league, page=page)
            if page == 1:
                path = injestion.core.raw_store.save_raw_to_json(
                    raw,
                    f"fixtures_{league}_page1_sample",
                    source="oddsjam",
                )
                print(f"Saved sample {league} page 1 -> {path}")

            fixture_rows = manager.raw_to_rows("oddsjam_fixtures", raw)
            inserted_fixture_rows = 0
            if fixture_rows:
                merge_stats = bq.merge_fixture_rows_by_fixture_id(fixtures_table_id, fixture_rows)
                inserted_fixture_rows = merge_stats["total_inserted_rows"]

            season_rows.extend(manager.raw_to_rows("oddsjam_seasons", raw))
            has_more = bool(raw.get("has_more"))
            print(
                (
                    f"  {league} page {page} (has_more={has_more}) -> {len(fixture_rows)} fixtures "
                    f"(inserted={inserted_fixture_rows})"
                )
            )

            if not has_more:
                break
            page += 1
            await asyncio.sleep(PAGE_DELAY_SECONDS)

        deduped_seasons = schema_seasons.dedupe_season_rows(season_rows)
        if deduped_seasons:
            bq.write_rows(seasons_table_id, deduped_seasons)
            print(f"  {league} -> {len(deduped_seasons)} unique seasons")

    print("Done.")
