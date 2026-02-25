"""
OddsJam odds pipeline: pull fixture_ids from BQ -> fetch (parallel) -> transform -> upload.
Closed loop: run in isolation via Runner.run("odds"). Depends on fixtures table being populated.
"""

import asyncio

from injestion.oddsjam.pipelines.concurrency import semaphore


async def run(client, manager, bq) -> None:
    """End-to-end: get fixture ids from BQ, fetch odds in parallel, write to BigQuery."""
    pass