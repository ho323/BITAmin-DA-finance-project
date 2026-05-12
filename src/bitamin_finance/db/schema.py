from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection

from bitamin_finance.config import PROJECT_ROOT


SCHEMA_PATH = PROJECT_ROOT / "sql" / "001_schema.sql"


def apply_schema(connection: Connection, schema_path: Path = SCHEMA_PATH) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    cursor = connection.connection.cursor()
    try:
        cursor.execute(sql)
    finally:
        cursor.close()


def ensure_partitions(connection: Connection, year: int) -> None:
    tables = [
        "fact_stock_daily",
        "fact_etf_daily",
        "fact_etf_holdings",
        "fact_market_index_daily",
        "fact_kfi_scores",
        "fact_event_validation",
    ]
    for table in tables:
        connection.execute(text("SELECT bitamin.ensure_year_partition(:table, :year)"), {
            "table": table,
            "year": year,
        })
