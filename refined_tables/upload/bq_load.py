"""
Load pandas DataFrames into BigQuery using load jobs (not streaming inserts).

Use injestion.core.bq.get_client() for the client so credentials match ingestion.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Literal

from google.cloud import bigquery

if TYPE_CHECKING:
    import pandas as pd

WriteDispositionName = Literal["WRITE_TRUNCATE", "WRITE_APPEND", "WRITE_EMPTY"]


def _is_refined_fixture_stats_table(table_id: str) -> bool:
    normalized = table_id.strip().lower()
    return normalized.endswith(".refined_fixture_stats") or normalized == "refined_fixture_stats"


def _prepare_special_case_dataframe(table_id: str, df):
    """
    Apply table-specific safeguards/transforms before upload.

    For refined_fixture_stats:
    - enforce one row per sport_event_id
    - stamp updated_at for the current load
    """
    if not _is_refined_fixture_stats_table(table_id):
        return df

    if "sport_event_id" not in df.columns:
        raise ValueError(
            "refined_fixture_stats upload requires 'sport_event_id' column."
        )

    null_id_count = int(df["sport_event_id"].isna().sum())
    if null_id_count > 0:
        raise ValueError(
            f"refined_fixture_stats has {null_id_count} rows with null sport_event_id."
        )

    dup_mask = df.duplicated(subset=["sport_event_id"], keep=False)
    duplicate_count = int(dup_mask.sum())
    if duplicate_count > 0:
        sample_ids = (
            df.loc[dup_mask, "sport_event_id"]
            .astype(str)
            .drop_duplicates()
            .head(10)
            .tolist()
        )
        raise ValueError(
            "refined_fixture_stats uniqueness guard failed: "
            f"{duplicate_count} duplicate rows on sport_event_id. "
            f"Sample IDs: {sample_ids}"
        )

    if "updated_at" in df.columns:
        import pandas as pd

        run_ts = pd.Timestamp.now(tz="UTC")
        df = df.copy()
        df["updated_at"] = run_ts

    return df


def _job_config(
    *,
    write_disposition: WriteDispositionName,
    schema: list[bigquery.SchemaField] | None,
    autodetect: bool,
) -> bigquery.LoadJobConfig:
    wd = getattr(bigquery.WriteDisposition, write_disposition)
    if autodetect:
        if schema:
            warnings.warn(
                "autodetect=True ignores an explicit schema; omit schema or set autodetect=False.",
                UserWarning,
                stacklevel=3,
            )
        return bigquery.LoadJobConfig(
            write_disposition=wd,
            autodetect=True,
        )
    if schema is None:
        raise ValueError(
            "Provide schema (e.g. module.get_schema()) or pass autodetect=True for exploratory loads."
        )
    if len(schema) == 0:
        raise ValueError(
            "schema is empty. Use get_schema() from the schema module, or autodetect=True; "
            "restart the notebook kernel if you recently changed schema code."
        )
    return bigquery.LoadJobConfig(
        write_disposition=wd,
        schema=schema,
    )


def load_dataframe(
    client: bigquery.Client,
    table_id: str,
    df: pd.DataFrame,
    *,
    write_disposition: WriteDispositionName = "WRITE_TRUNCATE",
    schema: list[bigquery.SchemaField] | None = None,
    autodetect: bool = False,
) -> bigquery.LoadJob:
    """
    Start a load job from a DataFrame into table_id.

    Blocks until the job completes; raises if the job fails.

    Parameters
    ----------
    client
        e.g. from injestion.core.bq.get_client()
    table_id
        project.dataset.table
    df
        Rows to load
    write_disposition
        WRITE_TRUNCATE (replace), WRITE_APPEND, or WRITE_EMPTY (fail if exists)
    schema
        Full table schema. Required unless autodetect=True.
    autodetect
        If True, infer schema from the DataFrame (omit or ignore schema for prod).
    """
    import pandas as pd  # noqa: F401 — runtime check for optional dep

    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"df must be a pandas DataFrame, got {type(df)!r}")

    prepared_df = _prepare_special_case_dataframe(table_id, df)

    job_config = _job_config(
        write_disposition=write_disposition,
        schema=schema,
        autodetect=autodetect,
    )
    job = client.load_table_from_dataframe(prepared_df, table_id, job_config=job_config)
    job.result()
    return job


def replace_table(
    client: bigquery.Client,
    table_id: str,
    df: pd.DataFrame,
    *,
    schema: list[bigquery.SchemaField] | None = None,
    autodetect: bool = False,
) -> bigquery.LoadJob:
    """Replace destination table contents with df (WRITE_TRUNCATE)."""
    return load_dataframe(
        client,
        table_id,
        df,
        write_disposition="WRITE_TRUNCATE",
        schema=schema,
        autodetect=autodetect,
    )


def append_table(
    client: bigquery.Client,
    table_id: str,
    df: pd.DataFrame,
    *,
    schema: list[bigquery.SchemaField] | None = None,
    autodetect: bool = False,
) -> bigquery.LoadJob:
    """Append df to destination table (WRITE_APPEND)."""
    return load_dataframe(
        client,
        table_id,
        df,
        write_disposition="WRITE_APPEND",
        schema=schema,
        autodetect=autodetect,
    )
