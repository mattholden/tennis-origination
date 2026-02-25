.PHONY: run sportradar-pipeline oddsjam-pipeline

run:
	uv run python -m runner

# Sportradar: run a pipeline by name (default: rankings).
# Example: make sportradar-pipeline PIPELINE=event_summary
PIPELINE ?= rankings
sportradar-pipeline:
	uv run python -m runner $(PIPELINE)

# OddsJam: run a pipeline by name (default: fixtures).
# Example: make oddsjam-pipeline ODDSJAM_PIPELINE=odds
ODDSJAM_PIPELINE ?= fixtures
oddsjam-pipeline:
	uv run python -m runner oddsjam $(ODDSJAM_PIPELINE)
