"""
Registry of pipeline names to run functions. Each pipeline is a closed loop.
"""

from injestion.oddsjam.pipelines.odds import run as odds_run
from injestion.oddsjam.pipelines.fixtures import run as fixtures_run

PIPELINES = {
    "odds": odds_run,
    "fixtures": fixtures_run,
}

def run_pipeline(name: str, client, manager, bq) -> None:
    """Run the pipeline for the given resource name. Raises if unknown."""
    if name not in PIPELINES:
        raise ValueError(
            f"Unknown pipeline: {name!r}. Known: {list(PIPELINES.keys())}"
        )
    PIPELINES[name](client, manager, bq)