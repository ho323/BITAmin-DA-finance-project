from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection


def _clean_value(value: Any) -> Any:
    if isinstance(value, float) and pd.isna(value):
        return None
    if pd.isna(value) if not isinstance(value, (dict, list, tuple)) else False:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def dataframe_records(df: pd.DataFrame, columns: Sequence[str]) -> list[dict[str, Any]]:
    records = []
    for row in df.reindex(columns=columns).to_dict("records"):
        records.append({key: _clean_value(value) for key, value in row.items()})
    return records


def upsert_dataframe(
    connection: Connection,
    df: pd.DataFrame,
    table: str,
    columns: Sequence[str],
    conflict_columns: Sequence[str],
    schema: str = "bitamin",
) -> int:
    if df.empty:
        return 0
    records = dataframe_records(df, columns)
    column_sql = ", ".join(columns)
    value_sql = ", ".join(
        f"CAST(:{column} AS jsonb)" if column.endswith("_flags") else f":{column}"
        for column in columns
    )
    update_columns = [column for column in columns if column not in conflict_columns]
    update_sql = ", ".join(
        f"{column} = EXCLUDED.{column}" for column in update_columns if column != "created_at"
    )
    update_sql = f"{update_sql}, updated_at = now()" if update_sql else "updated_at = now()"
    conflict_sql = ", ".join(conflict_columns)
    sql = text(
        f"""
        INSERT INTO {schema}.{table} ({column_sql})
        VALUES ({value_sql})
        ON CONFLICT ({conflict_sql}) DO UPDATE SET {update_sql}
        """
    )
    connection.execute(sql, records)
    return len(records)


def start_run(connection: Connection, job_name: str, parameters: dict[str, Any] | None = None) -> int:
    result = connection.execute(
        text(
            """
            INSERT INTO bitamin.etl_run_log (job_name, parameters)
            VALUES (:job_name, CAST(:parameters AS jsonb))
            RETURNING run_id
            """
        ),
        {"job_name": job_name, "parameters": json.dumps(parameters or {}, ensure_ascii=False)},
    )
    return int(result.scalar_one())


def finish_run(
    connection: Connection,
    run_id: int,
    status: str,
    row_count: int = 0,
    message: str | None = None,
) -> None:
    connection.execute(
        text(
            """
            UPDATE bitamin.etl_run_log
            SET finished_at = now(), status = :status, row_count = :row_count, message = :message
            WHERE run_id = :run_id
            """
        ),
        {"run_id": run_id, "status": status, "row_count": row_count, "message": message},
    )


def write_quality_check(
    connection: Connection,
    run_id: int,
    check_name: str,
    status: str,
    observed_value: float | None = None,
    threshold: float | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO bitamin.data_quality_check
                (run_id, check_name, status, observed_value, threshold, details)
            VALUES
                (:run_id, :check_name, :status, :observed_value, :threshold, CAST(:details AS jsonb))
            """
        ),
        {
            "run_id": run_id,
            "check_name": check_name,
            "status": status,
            "observed_value": observed_value,
            "threshold": threshold,
            "details": json.dumps(details or {}, ensure_ascii=False),
        },
    )
