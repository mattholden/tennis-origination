"""
Competitors pipeline: pull competitor_ids from BQ -> fetch -> transform -> upload.
Closed loop: run in isolation via Runner.run("competitors"). Depends on season_competitors table being populated.
"""

import core.raw_store


def run(client, manager, bq) -> None:
    """End-to-end: get competitor ids from BQ, fetch competitors, transform, write to BigQuery."""
    competitor_ids = bq.get_competitor_ids_from_season_competitors_table(
        manager.get_table_id("season_competitors")
    )

    all_raw_by_competitor = {}
    for competitor_id in competitor_ids:
        raw = manager.get_raw("competitors", client, competitor_id=competitor_id)
        all_raw_by_competitor[competitor_id] = raw

    core.raw_store.save_raw_to_json(
        {"by_competitor": all_raw_by_competitor},
        "competitors",
        source="sportradar",
    )