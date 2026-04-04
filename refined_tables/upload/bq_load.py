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

    job_config = _job_config(
        write_disposition=write_disposition,
        schema=schema,
        autodetect=autodetect,
    )
    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
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
