"""
OddsJam fixtures pipeline: incremental fixture import by league (ATP, WTA).
API calls -> schema transforms -> BQ upload. Saves first page per league as sample JSON.
"""

import asyncio
from datetime import timedelta

import injestion.core.raw_store
from injestion.oddsjam.fetch.fixtures import DEFAULT_START_DATE_AFTER
from injestion.oddsjam.schema import seasons as schema_seasons


LEAGUES = ("ATP", "WTA")
# LEAGUES = ("davis_cup", "laver_cup", "united_cup", "atp_challenger")
PAGE_DELAY_SECONDS = 0.5
FIXTURES_LOOKBACK_DAYS = 7


def _resolve_start_date_after(
    bq,
    fixtures_table_id: str,
    *,
    league: str,
) -> str:
    """
    Return an incremental lower bound for fixture fetches.

    Uses league-specific MAX(start_date) from BQ minus a small lookback window.
    Falls back to DEFAULT_START_DATE_AFTER when no historical rows exist.
    """
    max_start_date = bq.get_max_start_date_from_oddsjam_fixtures_table(
        fixtures_table_id,
        league_name=league,
    )
    if max_start_date is None:
        return DEFAULT_START_DATE_AFTER

    incremental_start = (max_start_date - timedelta(days=FIXTURES_LOOKBACK_DAYS)).date().isoformat()
    return max(incremental_start, DEFAULT_START_DATE_AFTER)


async def run(client, manager, bq) -> None:
    """Fetch fixture pages incrementally per league; transform and write fixtures and seasons to BQ."""
    fixtures_table_id = manager.get_table_id("oddsjam_fixtures")
    seasons_table_id = manager.get_table_id("oddsjam_seasons")

    for league in LEAGUES:
        season_rows: list[dict] = []
        page = 1
        start_date_after = _resolve_start_date_after(bq, fixtures_table_id, league=league)
        print(
            (
                f"Fixtures incremental window for {league}: "
                f"start_date_after={start_date_after} (lookback_days={FIXTURES_LOOKBACK_DAYS})"
            ),
            flush=True,
        )

        while True:
            raw = await manager.get_raw_async(
                "oddsjam_fixtures",
                client,
                league=league,
                page=page,
                start_date_after=start_date_after,
            )
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
