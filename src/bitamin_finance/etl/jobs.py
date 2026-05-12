from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection

from bitamin_finance.data.krx_client import KRXClient
from bitamin_finance.db.schema import ensure_partitions
from bitamin_finance.etl.loaders import (
    finish_run,
    start_run,
    upsert_dataframe,
    write_quality_check,
)
from bitamin_finance.features.kfi import compute_kfi_scores
from bitamin_finance.validation.event_study import build_event_validation_frame


STOCK_DIM_COLUMNS = ["ticker", "name", "market", "is_active"]
STOCK_DAILY_COLUMNS = [
    "trade_date",
    "ticker",
    "market",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trading_value",
    "market_cap",
    "listed_shares",
    "listed_shares_proxy",
    "data_quality_flags",
]
ETF_DIM_COLUMNS = [
    "etf_ticker",
    "name",
    "issuer",
    "asset_class",
    "is_leveraged",
    "is_inverse",
    "is_synthetic",
    "is_foreign_underlying",
]
ETF_DAILY_COLUMNS = [
    "trade_date",
    "etf_ticker",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trading_value",
    "nav",
    "deviation_rate",
    "tracking_error_rate",
    "data_quality_flags",
]
ETF_HOLDING_COLUMNS = [
    "as_of_date",
    "etf_ticker",
    "stock_ticker",
    "shares",
    "valuation_amount",
    "weight",
    "data_quality_flags",
]
MARKET_INDEX_COLUMNS = [
    "trade_date",
    "index_code",
    "index_name",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trading_value",
    "market_cap",
]
KFI_COLUMNS = [
    "score_date",
    "ticker",
    "index_version",
    "ownership_pressure",
    "liquidity_pressure",
    "leveraged_inverse_pressure",
    "deviation_stress",
    "flow_stress",
    "kfi_base",
    "kfi_korea",
    "data_quality_flags",
]
EVENT_COLUMNS = [
    "event_date",
    "ticker",
    "index_version",
    "stock_return",
    "market_return",
    "excess_drop",
    "kfi_base",
    "kfi_korea",
    "market_cap",
    "volatility_20d",
    "turnover",
    "beta",
    "decile",
    "data_quality_flags",
]


def ingest_stock_daily(
    connection: Connection,
    trade_date: str,
    client: KRXClient | None = None,
) -> int:
    client = client or KRXClient()
    ensure_partitions(connection, date.fromisoformat(trade_date).year)
    run_id = start_run(connection, "stock_daily_ingest", {"trade_date": trade_date})
    try:
        universe = client.collect_stock_universe(trade_date)
        daily = client.collect_stock_daily(trade_date)
        dim_count = upsert_dataframe(connection, universe, "dim_stock", STOCK_DIM_COLUMNS, ["ticker"])
        fact_count = upsert_dataframe(
            connection,
            daily,
            "fact_stock_daily",
            STOCK_DAILY_COLUMNS,
            ["trade_date", "ticker"],
        )
        write_quality_check(
            connection,
            run_id,
            "stock_daily_non_empty",
            "pass" if fact_count > 0 else "fail",
            observed_value=fact_count,
            threshold=1,
            details={"dim_rows": dim_count},
        )
        finish_run(connection, run_id, "success", fact_count)
        return fact_count
    except Exception as exc:
        finish_run(connection, run_id, "failed", message=str(exc))
        raise


def ingest_etf_daily(
    connection: Connection,
    trade_date: str,
    client: KRXClient | None = None,
    max_etfs: int | None = None,
) -> int:
    client = client or KRXClient()
    ensure_partitions(connection, date.fromisoformat(trade_date).year)
    run_id = start_run(connection, "etf_daily_ingest", {"trade_date": trade_date, "max_etfs": max_etfs})
    try:
        universe = client.collect_etf_universe(trade_date)
        daily = client.collect_etf_daily(trade_date, max_etfs=max_etfs)
        holdings = client.collect_etf_holdings(trade_date, max_etfs=max_etfs)
        dim_count = upsert_dataframe(connection, universe, "dim_etf", ETF_DIM_COLUMNS, ["etf_ticker"])
        daily_count = upsert_dataframe(
            connection, daily, "fact_etf_daily", ETF_DAILY_COLUMNS, ["trade_date", "etf_ticker"]
        )
        holding_count = upsert_dataframe(
            connection,
            holdings,
            "fact_etf_holdings",
            ETF_HOLDING_COLUMNS,
            ["as_of_date", "etf_ticker", "stock_ticker"],
        )
        total = daily_count + holding_count
        write_quality_check(
            connection,
            run_id,
            "etf_holdings_matchable",
            "pass" if holdings.empty or holdings["stock_ticker"].notna().mean() >= 0.95 else "warn",
            observed_value=None if holdings.empty else float(holdings["stock_ticker"].notna().mean()),
            threshold=0.95,
            details={"dim_rows": dim_count, "daily_rows": daily_count, "holding_rows": holding_count},
        )
        finish_run(connection, run_id, "success", total)
        return total
    except Exception as exc:
        finish_run(connection, run_id, "failed", message=str(exc))
        raise


def ingest_market_index_daily(
    connection: Connection,
    trade_date: str,
    client: KRXClient | None = None,
) -> int:
    client = client or KRXClient()
    ensure_partitions(connection, date.fromisoformat(trade_date).year)
    run_id = start_run(connection, "market_index_daily_ingest", {"trade_date": trade_date})
    try:
        index_daily = client.collect_market_index_daily(trade_date)
        count = upsert_dataframe(
            connection,
            index_daily,
            "fact_market_index_daily",
            MARKET_INDEX_COLUMNS,
            ["trade_date", "index_code"],
        )
        write_quality_check(
            connection,
            run_id,
            "market_index_non_empty",
            "pass" if count > 0 else "warn",
            observed_value=count,
            threshold=1,
        )
        finish_run(connection, run_id, "success", count)
        return count
    except Exception as exc:
        finish_run(connection, run_id, "failed", message=str(exc))
        raise


def _read_sql(connection: Connection, sql: str, params: dict[str, object]) -> pd.DataFrame:
    result = connection.execute(text(sql), params)
    return pd.DataFrame(result.fetchall(), columns=result.keys())


def build_kfi_scores_from_db(connection: Connection, score_date: str, lookback_days: int = 40) -> pd.DataFrame:
    stock_daily = _read_sql(
        connection,
        "SELECT * FROM bitamin.fact_stock_daily WHERE trade_date = :score_date",
        {"score_date": score_date},
    )
    stock_history = _read_sql(
        connection,
        """
        SELECT *
        FROM bitamin.fact_stock_daily
        WHERE trade_date BETWEEN CAST(:score_date AS date) - CAST(:lookback AS integer)
                            AND CAST(:score_date AS date)
        """,
        {"score_date": score_date, "lookback": lookback_days},
    )
    etf_daily = _read_sql(
        connection,
        """
        SELECT d.*, e.is_leveraged, e.is_inverse, e.is_synthetic, e.is_foreign_underlying
        FROM bitamin.fact_etf_daily d
        LEFT JOIN bitamin.dim_etf e USING (etf_ticker)
        WHERE d.trade_date BETWEEN CAST(:score_date AS date) - CAST(:lookback AS integer)
                              AND CAST(:score_date AS date)
        """,
        {"score_date": score_date, "lookback": lookback_days},
    )
    etf_holdings = _read_sql(
        connection,
        "SELECT * FROM bitamin.fact_etf_holdings WHERE as_of_date = :score_date",
        {"score_date": score_date},
    )
    return build_kfi_scores(
        connection,
        score_date,
        stock_daily=stock_daily,
        etf_holdings=etf_holdings,
        etf_daily=etf_daily,
        stock_history=stock_history,
    )


def build_event_validation_from_db(
    connection: Connection,
    event_date: str,
    score_date: str | None = None,
    market_index: str = "KOSPI",
    lookback_days: int = 60,
) -> pd.DataFrame:
    score_date = score_date or event_date
    stock_history = _read_sql(
        connection,
        """
        SELECT *
        FROM bitamin.fact_stock_daily
        WHERE trade_date BETWEEN CAST(:event_date AS date) - CAST(:lookback AS integer)
                            AND CAST(:event_date AS date)
        """,
        {"event_date": event_date, "lookback": lookback_days},
    )
    market_history = _read_sql(
        connection,
        """
        SELECT *
        FROM bitamin.fact_market_index_daily
        WHERE index_name = :market_index
          AND trade_date BETWEEN CAST(:event_date AS date) - CAST(:lookback AS integer)
                             AND CAST(:event_date AS date)
        """,
        {"event_date": event_date, "market_index": market_index, "lookback": lookback_days},
    )
    kfi_scores = _read_sql(
        connection,
        "SELECT * FROM bitamin.fact_kfi_scores WHERE score_date = :score_date",
        {"score_date": score_date},
    )
    return build_event_validation(connection, event_date, stock_history, market_history, kfi_scores)


def build_kfi_scores(
    connection: Connection,
    score_date: str,
    stock_daily: pd.DataFrame,
    etf_holdings: pd.DataFrame,
    etf_daily: pd.DataFrame,
    stock_history: pd.DataFrame,
) -> pd.DataFrame:
    ensure_partitions(connection, date.fromisoformat(score_date).year)
    run_id = start_run(connection, "kfi_build", {"score_date": score_date})
    try:
        scores = compute_kfi_scores(
            score_date=score_date,
            stock_daily=stock_daily,
            etf_holdings=etf_holdings,
            etf_daily=etf_daily,
            stock_history=stock_history,
        )
        count = upsert_dataframe(
            connection,
            scores,
            "fact_kfi_scores",
            KFI_COLUMNS,
            ["score_date", "ticker", "index_version"],
        )
        write_quality_check(
            connection,
            run_id,
            "kfi_scores_non_empty",
            "pass" if count > 0 else "fail",
            observed_value=count,
            threshold=1,
        )
        finish_run(connection, run_id, "success", count)
        return scores
    except Exception as exc:
        finish_run(connection, run_id, "failed", message=str(exc))
        raise


def build_event_validation(
    connection: Connection,
    event_date: str,
    stock_history: pd.DataFrame,
    market_history: pd.DataFrame,
    kfi_scores: pd.DataFrame,
) -> pd.DataFrame:
    ensure_partitions(connection, date.fromisoformat(event_date).year)
    run_id = start_run(connection, "kfi_validation", {"event_date": event_date})
    try:
        validation = build_event_validation_frame(
            event_date=event_date,
            stock_history=stock_history,
            market_history=market_history,
            kfi_scores=kfi_scores,
        )
        count = upsert_dataframe(
            connection,
            validation,
            "fact_event_validation",
            EVENT_COLUMNS,
            ["event_date", "ticker", "index_version"],
        )
        finish_run(connection, run_id, "success", count)
        return validation
    except Exception as exc:
        finish_run(connection, run_id, "failed", message=str(exc))
        raise
