.PHONY: run sportradar-pipeline oddsjam-pipeline oj-pipeline-fixtures oj-pipeline-odds oj-pipeline-results oj-pipeline-incremental

run:
	uv run python -m injestion.runner

# Sportradar: run a pipeline by name

sr-pipeline-event_summary:
	uv run python -m injestion.runner sportradar event_summary

sr-pipeline-rankings:
	uv run python -m injestion.runner sportradar rankings

sr-pipeline-seasons:
	uv run python -m injestion.runner sportradar seasons

sr-pipeline-season_competitors:
	uv run python -m injestion.runner sportradar season_competitors

sr-pipeline-competitors:
	uv run python -m injestion.runner sportradar competitors

sr-pipeline-season_brackets:
	uv run python -m injestion.runner sportradar season_brackets

sr-pipeline-event_summary:
	uv run python -m injestion.runner sportradar event_summary
	
# OddsJam: run a pipeline by name
oj-pipeline-fixtures:
	uv run python -m injestion.runner oddsjam fixtures

oj-pipeline-odds:
	uv run python -m injestion.runner oddsjam odds

oj-pipeline-results:
	uv run python -m injestion.runner oddsjam results

oj-pipeline-incremental:
	uv run python -m injestion.runner oddsjam fixtures && uv run python -m injestion.runner oddsjam odds && uv run python -m injestion.runner oddsjam results