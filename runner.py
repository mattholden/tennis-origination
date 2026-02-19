"""
Entry point: load .env once, then run resource pipelines.

Each pipeline is a closed loop: (optional) pull params from BigQuery -> fetch -> transform -> upload.
Run one pipeline in isolation with Runner.run(name). All pipelines are async and run under asyncio.
"""

import asyncio

from core.env import load_env

# Load .env from project root so client, config, etc. can use os.environ
load_env()


class Runner:
    """
    Holds client, manager, and BQ; runs resource pipelines by name.
    Each pipeline is self-contained and can be tested in isolation.
    """

    def __init__(self, client, manager, bq):
        """
        client: API client (e.g. SportradarClient). Pipelines use client.get_async() for fetch.
        manager: Source manager (e.g. SportradarManager).
        bq: BigQuery interface.
        """
        self._client = client
        self._manager = manager
        self._bq = bq
        self._pipelines = {}  # name -> async run(client, manager, bq)

    def register(self, name: str, pipeline_fn) -> None:
        """Register a pipeline. pipeline_fn must be async (client, manager, bq) -> None."""
        self._pipelines[name] = pipeline_fn

    def run(self, name: str) -> None:
        """Run the pipeline for the given resource. Raises if unknown."""
        if name not in self._pipelines:
            raise ValueError(
                f"Unknown pipeline: {name!r}. Known: {list(self._pipelines.keys())}"
            )
        fn = self._pipelines[name]
        asyncio.run(fn(self._client, self._manager, self._bq))

    def list_pipelines(self) -> list[str]:
        """Return registered pipeline names."""
        return list(self._pipelines.keys())


def create_sportradar_runner() -> Runner:
    """Build a Runner with Sportradar client, manager, and BQ; registers Sportradar pipelines."""
    from injestion.sportradar import SportradarClient, SportradarManager
    from injestion.sportradar.pipelines.registry import PIPELINES

    import core.bq as bq

    client = SportradarClient()
    manager = SportradarManager()
    runner = Runner(client, manager, bq)
    for name, fn in PIPELINES.items():
        runner.register(name, fn)
    return runner


if __name__ == "__main__":
    runner = create_sportradar_runner()
    print("Pipelines:", runner.list_pipelines())
    # Run one in isolation, e.g.:
    runner.run("event_summary")
