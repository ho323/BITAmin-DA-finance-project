from __future__ import annotations

import pendulum

from airflow import DAG
from airflow.operators.python import PythonOperator

from bitamin_finance.db.connection import begin_connection
from bitamin_finance.etl.jobs import (
    build_event_validation_from_db,
    build_kfi_scores_from_db,
    ingest_etf_daily,
    ingest_market_index_daily,
    ingest_stock_daily,
)


DEFAULT_ARGS = {"owner": "bitamin", "retries": 1}
SCHEDULE = "0 19 * * 1-5"
SEOUL = pendulum.timezone("Asia/Seoul")


def _stock_daily_ingest(**context) -> None:
    trade_date = context["ds"]
    with begin_connection() as connection:
        ingest_stock_daily(connection, trade_date)
        ingest_market_index_daily(connection, trade_date)


def _etf_daily_ingest(**context) -> None:
    trade_date = context["ds"]
    with begin_connection() as connection:
        ingest_etf_daily(connection, trade_date)


def _kfi_build(**context) -> None:
    score_date = context["ds"]
    with begin_connection() as connection:
        build_kfi_scores_from_db(connection, score_date)


def _kfi_validation(**context) -> None:
    event_date = context["dag_run"].conf.get("event_date", context["ds"])
    score_date = context["dag_run"].conf.get("score_date", event_date)
    market_index = context["dag_run"].conf.get("market_index", "KOSPI")
    with begin_connection() as connection:
        build_event_validation_from_db(connection, event_date, score_date, market_index=market_index)


with DAG(
    dag_id="dag_stock_daily_ingest",
    default_args=DEFAULT_ARGS,
    schedule=SCHEDULE,
    start_date=pendulum.datetime(2026, 1, 1, tz=SEOUL),
    catchup=False,
    tags=["bitamin", "krx", "stock"],
) as dag_stock_daily_ingest:
    PythonOperator(task_id="ingest_stock_and_market_index", python_callable=_stock_daily_ingest)


with DAG(
    dag_id="dag_etf_daily_ingest",
    default_args=DEFAULT_ARGS,
    schedule=SCHEDULE,
    start_date=pendulum.datetime(2026, 1, 1, tz=SEOUL),
    catchup=False,
    tags=["bitamin", "krx", "etf"],
) as dag_etf_daily_ingest:
    PythonOperator(task_id="ingest_etf_daily_and_holdings", python_callable=_etf_daily_ingest)


with DAG(
    dag_id="dag_kfi_build",
    default_args=DEFAULT_ARGS,
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz=SEOUL),
    catchup=False,
    tags=["bitamin", "kfi"],
) as dag_kfi_build:
    PythonOperator(task_id="build_kfi_scores", python_callable=_kfi_build)


with DAG(
    dag_id="dag_kfi_validation",
    default_args=DEFAULT_ARGS,
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz=SEOUL),
    catchup=False,
    tags=["bitamin", "validation"],
) as dag_kfi_validation:
    PythonOperator(task_id="build_event_validation", python_callable=_kfi_validation)

