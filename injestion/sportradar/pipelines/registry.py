"""
Registry of pipeline names to run functions. Each pipeline is a closed loop.

Imports run from each pipeline module directly to avoid circular import
(pipelines/__init__.py imports this registry).
"""

from injestion.sportradar.pipelines.competitions import run as competitions_run
from injestion.sportradar.pipelines.seasons import run as seasons_run
from injestion.sportradar.pipelines.season_competitors import run as season_competitors_run
from injestion.sportradar.pipelines.competitors import run as competitors_run
from injestion.sportradar.pipelines.season_brackets import run as season_brackets_run

# name -> run(client, manager, bq)
PIPELINES = {
    "competitions": competitions_run,
    "seasons": seasons_run,
    "season_competitors": season_competitors_run,
    "competitors": competitors_run,
    "season_brackets": season_brackets_run,
}


def run_pipeline(name: str, client, manager, bq) -> None:
    """Run the pipeline for the given resource name. Raises if unknown."""
    if name not in PIPELINES:
        raise ValueError(
            f"Unknown pipeline: {name!r}. Known: {list(PIPELINES.keys())}"
        )
    PIPELINES[name](client, manager, bq)
