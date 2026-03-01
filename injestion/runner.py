"""
Entry point: load .env once, then run resource pipelines.

Each pipeline is a closed loop: (optional) pull params from BigQuery -> fetch -> transform -> upload.
Run one pipeline in isolation with Runner.run(name). All pipelines are async and run under asyncio.
"""

import asyncio

from injestion.core.env import load_env

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

    import injestion.core.bq as bq

    client = SportradarClient()
    manager = SportradarManager()
    runner = Runner(client, manager, bq)
    for name, fn in PIPELINES.items():
        runner.register(name, fn)
    return runner


def create_oddsjam_runner() -> Runner:
    """Build a Runner with OpticOdds client, OddsJam manager, and BQ; registers OddsJam pipelines."""
    from injestion.oddsjam import OpticOddsClient, OddsJamManager
    from injestion.oddsjam.pipelines.registry import PIPELINES

    import injestion.core.bq as bq

    client = OpticOddsClient()
    manager = OddsJamManager()
    runner = Runner(client, manager, bq)
    for name, fn in PIPELINES.items():
        runner.register(name, fn)
    return runner


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "oddsjam":
        runner = create_oddsjam_runner()
        pipelines = runner.list_pipelines()
        print("OddsJam pipelines:", pipelines)
        if len(sys.argv) > 2:
            pipeline_name = sys.argv[2]
            if pipeline_name not in pipelines:
                print(f"Unknown pipeline: {pipeline_name}")
                sys.exit(1)
            runner.run(pipeline_name)
        else:
            print("Usage: python -m injestion.runner oddsjam [pipeline_name]")
            sys.exit(1)
    elif len(sys.argv) > 1 and sys.argv[1] == "sportradar":
        runner = create_sportradar_runner()
        pipelines = runner.list_pipelines()
        print("SportRadar pipelines:", pipelines)
        if len(sys.argv) > 2:
            pipeline_name = sys.argv[2]
            if pipeline_name not in pipelines:
                print(f"Unknown pipeline: {pipeline_name}")
                sys.exit(1)
            runner.run(pipeline_name)
        else:
            print("Usage: python -m injestion.runner sportradar [pipeline_name]")
            sys.exit(1)
    else:
        print("Usage: python -m injestion.runner [oddsjam | sportradar] [pipeline_name]")
        sys.exit(1)
