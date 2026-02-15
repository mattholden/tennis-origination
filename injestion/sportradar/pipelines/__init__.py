"""
Sportradar resource pipelines: each is a closed loop.

Pipeline = (optional) pull params from BigQuery -> fetch -> transform -> upload.
Each pipeline can be run in isolation via Runner.run(name).
"""

from injestion.sportradar.pipelines.registry import PIPELINES, run_pipeline

__all__ = ["PIPELINES", "run_pipeline"]
