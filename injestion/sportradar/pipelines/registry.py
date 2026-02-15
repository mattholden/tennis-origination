"""
Registry of pipeline names to run functions. Each pipeline is a closed loop.
"""

from injestion.sportradar.pipelines import competitions as competitions_pipeline

# name -> run(client, manager, bq)
PIPELINES = {
    "competitions": competitions_pipeline.run,
}


def run_pipeline(name: str, client, manager, bq) -> None:
    """Run the pipeline for the given resource name. Raises if unknown."""
    if name not in PIPELINES:
        raise ValueError(
            f"Unknown pipeline: {name!r}. Known: {list(PIPELINES.keys())}"
        )
    PIPELINES[name](client, manager, bq)
