"""
Registry of pipeline names to run functions. Each pipeline is a closed loop.
"""

from injestion.sportradar.pipelines import competitions as competitions_pipeline
from injestion.sportradar.pipelines import seasons as seasons_pipeline
from injestion.sportradar.pipelines import season_competitors as season_competitors_pipeline
from injestion.sportradar.pipelines import competitors as competitors_pipeline

# name -> run(client, manager, bq)
PIPELINES = {
    "competitions": competitions_pipeline.run,
    "seasons": seasons_pipeline.run,
    "season_competitors": season_competitors_pipeline.run,
    "competitors": competitors_pipeline.run,
}


def run_pipeline(name: str, client, manager, bq) -> None:
    """Run the pipeline for the given resource name. Raises if unknown."""
    if name not in PIPELINES:
        raise ValueError(
            f"Unknown pipeline: {name!r}. Known: {list(PIPELINES.keys())}"
        )
    PIPELINES[name](client, manager, bq)
