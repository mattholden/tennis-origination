.PHONY: run sportradar-pipeline oddsjam-pipeline oj-pipeline-fixtures oj-pipeline-odds oj-pipeline-results oj-pipeline-incremental

SR_SEASON_COMPETITORS_FAILED_ONLY ?= 0
SR_SEASON_COMPETITORS_FAILED_IDS_JSON ?= raw_data/sportradar/failed_processes/season_competitors_failed_season_ids.json
SR_SEASON_BRACKETS_FAILED_ONLY ?= 0
SR_SEASON_BRACKETS_FAILED_IDS_JSON ?= raw_data/sportradar/failed_processes/season_brackets_failed_season_ids.json
SR_EVENT_SUMMARY_FAILED_ONLY ?= 0
SR_EVENT_SUMMARY_FAILED_IDS_JSON ?= raw_data/sportradar/failed_processes/event_summary_failed_sport_event_ids.json
SR_EVENT_SUMMARY_MAX_CONCURRENT ?= 8
SR_EVENT_SUMMARY_PROGRESS_LOG_EVERY ?= 100
SR_EVENT_SUMMARY_WRITE_BATCH_EVENTS ?= 50

run:
	uv run python -m injestion.runner

# Sportradar: run a pipeline by name

sr-pipeline-event_summary:
	@if [ "$(SR_EVENT_SUMMARY_FAILED_ONLY)" = "1" ]; then \
		echo "Running event_summary in failed-only mode from $(SR_EVENT_SUMMARY_FAILED_IDS_JSON)"; \
		SR_EVENT_SUMMARY_IDS_JSON="$(SR_EVENT_SUMMARY_FAILED_IDS_JSON)" \
		SR_EVENT_SUMMARY_MAX_CONCURRENT="$(SR_EVENT_SUMMARY_MAX_CONCURRENT)" \
		SR_EVENT_SUMMARY_PROGRESS_LOG_EVERY="$(SR_EVENT_SUMMARY_PROGRESS_LOG_EVERY)" \
		SR_EVENT_SUMMARY_WRITE_BATCH_EVENTS="$(SR_EVENT_SUMMARY_WRITE_BATCH_EVENTS)" \
		uv run python -m injestion.runner sportradar event_summary; \
	else \
		SR_EVENT_SUMMARY_MAX_CONCURRENT="$(SR_EVENT_SUMMARY_MAX_CONCURRENT)" \
		SR_EVENT_SUMMARY_PROGRESS_LOG_EVERY="$(SR_EVENT_SUMMARY_PROGRESS_LOG_EVERY)" \
		SR_EVENT_SUMMARY_WRITE_BATCH_EVENTS="$(SR_EVENT_SUMMARY_WRITE_BATCH_EVENTS)" \
		uv run python -m injestion.runner sportradar event_summary; \
	fi

sr-pipeline-rankings:
	uv run python -m injestion.runner sportradar rankings

sr-pipeline-seasons:
	uv run python -m injestion.runner sportradar seasons

sr-pipeline-season_competitors:
	@if [ "$(SR_SEASON_COMPETITORS_FAILED_ONLY)" = "1" ]; then \
		echo "Running season_competitors in failed-only mode from $(SR_SEASON_COMPETITORS_FAILED_IDS_JSON)"; \
		SR_SEASON_COMPETITORS_IDS_JSON="$(SR_SEASON_COMPETITORS_FAILED_IDS_JSON)" uv run python -m injestion.runner sportradar season_competitors; \
	else \
		uv run python -m injestion.runner sportradar season_competitors; \
	fi

sr-pipeline-competitors:
	uv run python -m injestion.runner sportradar competitors

sr-pipeline-season_brackets:
	@if [ "$(SR_SEASON_BRACKETS_FAILED_ONLY)" = "1" ]; then \
		echo "Running season_brackets in failed-only mode from $(SR_SEASON_BRACKETS_FAILED_IDS_JSON)"; \
		SR_SEASON_BRACKETS_IDS_JSON="$(SR_SEASON_BRACKETS_FAILED_IDS_JSON)" uv run python -m injestion.runner sportradar season_brackets; \
	else \
		uv run python -m injestion.runner sportradar season_brackets; \
	fi

# OddsJam: run a pipeline by name
oj-pipeline-fixtures:
	uv run python -m injestion.runner oddsjam fixtures

oj-pipeline-odds:
	uv run python -m injestion.runner oddsjam odds

oj-pipeline-results:
	uv run python -m injestion.runner oddsjam results

oj-pipeline-incremental:
	uv run python -m injestion.runner oddsjam fixtures && uv run python -m injestion.runner oddsjam odds && uv run python -m injestion.runner oddsjam results