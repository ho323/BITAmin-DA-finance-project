from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from bitamin_finance.config import load_settings
from bitamin_finance.data.krx_client import KRXClient, KRXDataError
from bitamin_finance.db.connection import begin_connection
from bitamin_finance.db.schema import apply_schema
from bitamin_finance.etl.jobs import ingest_etf_daily, ingest_market_index_daily, ingest_stock_daily
from bitamin_finance.features.exposure import (
    build_etf_constituent_tables,
    build_stock_etf_exposure,
    export_etf_constituents,
    export_stock_etf_exposure,
    filter_exposure_candidates,
)
from bitamin_finance.features.kfi import compute_kfi_scores
from bitamin_finance.reporting.exports import export_validation_report
from bitamin_finance.validation.event_study import build_event_validation_frame


def cmd_init_db(_: argparse.Namespace) -> None:
    with begin_connection() as connection:
        apply_schema(connection)
    print("Database schema applied.")


def cmd_ingest(args: argparse.Namespace) -> None:
    with begin_connection() as connection:
        if args.target in {"stock", "all"}:
            rows = ingest_stock_daily(connection, args.date)
            print(f"Loaded stock daily rows: {rows}")
        if args.target in {"etf", "all"}:
            rows = ingest_etf_daily(connection, args.date, max_etfs=args.max_etfs)
            print(f"Loaded ETF rows: {rows}")
        if args.target in {"market-index", "all"}:
            rows = ingest_market_index_daily(connection, args.date)
            print(f"Loaded market index rows: {rows}")


def cmd_backfill(args: argparse.Namespace) -> None:
    dates = pd.date_range(args.start_date, args.end_date, freq="B")
    with begin_connection() as connection:
        for ts in dates:
            trade_date = ts.date().isoformat()
            print(f"[{trade_date}] ingest target={args.target}")
            if args.target in {"stock", "all"}:
                print(f"  stock rows: {ingest_stock_daily(connection, trade_date)}")
            if args.target in {"market-index", "all"}:
                print(f"  market index rows: {ingest_market_index_daily(connection, trade_date)}")
            if args.target in {"etf", "all"}:
                print(f"  etf rows: {ingest_etf_daily(connection, trade_date, max_etfs=args.max_etfs)}")


def _read_db_frame(sql: str, params: dict[str, object]) -> pd.DataFrame:
    with begin_connection() as connection:
        result = connection.execute(text(sql), params)
        return pd.DataFrame(result.fetchall(), columns=result.keys())


def _parse_filter_values(values: list[str] | None) -> list[str]:
    if not values:
        return []
    parsed: list[str] = []
    for value in values:
        parsed.extend(item.strip() for item in value.split(",") if item.strip())
    return parsed


def _add_in_filter(
    conditions: list[str],
    params: dict[str, object],
    column: str,
    param_prefix: str,
    values: list[str],
) -> None:
    if not values:
        return
    placeholders = []
    for index, value in enumerate(values):
        key = f"{param_prefix}_{index}"
        placeholders.append(f":{key}")
        params[key] = value
    conditions.append(f"{column} IN ({', '.join(placeholders)})")


def cmd_export_timeseries(args: argparse.Namespace) -> None:
    params: dict[str, object] = {"start_date": args.start_date, "end_date": args.end_date}
    conditions = [f"{args.date_column} BETWEEN :start_date AND :end_date"]
    order_by = args.order_by

    tickers = _parse_filter_values(args.ticker)
    etf_tickers = _parse_filter_values(args.etf_ticker)
    index_codes = _parse_filter_values(args.index_code)
    index_names = _parse_filter_values(args.index_name)

    _add_in_filter(conditions, params, args.ticker_column, "ticker", tickers)
    _add_in_filter(conditions, params, args.etf_ticker_column, "etf_ticker", etf_tickers)
    _add_in_filter(conditions, params, "index_code", "index_code", index_codes)
    _add_in_filter(conditions, params, "index_name", "index_name", index_names)

    sql = f"""
        {args.select_sql}
        WHERE {' AND '.join(conditions)}
        ORDER BY {order_by}
    """
    df = _read_db_frame(sql, params)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)
    print(f"Wrote {len(df)} rows to {output}")


def _collect_exposure_live(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    client = KRXClient()
    stock_universe = client.collect_stock_universe(args.date)
    stock_daily = client.collect_stock_daily(args.date)
    etf_universe = client.collect_etf_universe(args.date)
    etf_holdings = client.collect_etf_holdings(args.date, max_etfs=args.max_etfs)
    return build_stock_etf_exposure(stock_daily, etf_holdings, stock_universe, etf_universe)


def _collect_exposure_from_db(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    params = {"date": args.date}
    stock_daily = _read_db_frame(
        "SELECT * FROM bitamin.fact_stock_daily WHERE trade_date = :date",
        params,
    )
    stock_universe = _read_db_frame("SELECT * FROM bitamin.dim_stock", params)
    etf_universe = _read_db_frame("SELECT * FROM bitamin.dim_etf", params)
    etf_holdings = _read_db_frame(
        "SELECT * FROM bitamin.fact_etf_holdings WHERE as_of_date = :date",
        params,
    )
    return build_stock_etf_exposure(stock_daily, etf_holdings, stock_universe, etf_universe)


def cmd_export_exposure(args: argparse.Namespace) -> None:
    summary, detail, matrix = (
        _collect_exposure_from_db(args) if args.from_db else _collect_exposure_live(args)
    )
    output_dir = Path(args.output_dir)
    prefix = args.date.replace("-", "")
    paths = export_stock_etf_exposure(output_dir, summary, detail, matrix, prefix)
    etf_summary, etf_constituents = build_etf_constituent_tables(detail)
    etf_paths = export_etf_constituents(output_dir, etf_summary, etf_constituents, prefix)
    candidates = filter_exposure_candidates(
        summary,
        min_ownership_ratio=args.min_ownership_ratio,
        min_etf_count=args.min_etf_count,
        top_n=args.top_n,
    )
    candidate_path = output_dir / f"{prefix}_candidate_stocks.csv"
    candidates.to_csv(candidate_path, index=False)
    for name, path in {**paths, **etf_paths, "candidates": candidate_path}.items():
        print(f"{name}: {path}")
    print(f"summary rows: {len(summary)}")
    print(f"detail rows: {len(detail)}")
    print(f"etf summary rows: {len(etf_summary)}")
    print(f"etf constituent rows: {len(etf_constituents)}")
    print(f"candidate rows: {len(candidates)}")


def cmd_build_kfi(args: argparse.Namespace) -> None:
    client = KRXClient()
    stock_history = client.collect_recent_stock_history(args.date, lookback_days=args.lookback_days)
    stock_daily = stock_history.loc[stock_history["trade_date"] == args.date].copy()
    etf_daily = client.collect_etf_daily(args.date, max_etfs=args.max_etfs)
    etf_holdings = client.collect_etf_holdings(args.date, max_etfs=args.max_etfs)
    scores = compute_kfi_scores(args.date, stock_daily, etf_holdings, etf_daily, stock_history)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    scores.to_parquet(output, index=False)
    print(f"Wrote {len(scores)} K-FI rows to {output}")


def cmd_validate(args: argparse.Namespace) -> None:
    settings = load_settings()
    stock_history = pd.read_parquet(args.stock_history)
    market_history = pd.read_parquet(args.market_history)
    kfi_scores = pd.read_parquet(args.kfi_scores)
    validation = build_event_validation_frame(args.event_date, stock_history, market_history, kfi_scores)
    paths = export_validation_report(validation, settings.report_dir, f"kfi_{args.event_date}")
    for name, path in paths.items():
        print(f"{name}: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BITAmin Korean Fragility Index pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    init_db = sub.add_parser("init-db")
    init_db.set_defaults(func=cmd_init_db)

    ingest = sub.add_parser("ingest")
    ingest.add_argument("--date", required=True, help="YYYY-MM-DD")
    ingest.add_argument("--target", choices=["stock", "etf", "market-index", "all"], default="all")
    ingest.add_argument("--max-etfs", type=int, default=None)
    ingest.set_defaults(func=cmd_ingest)

    backfill = sub.add_parser("backfill")
    backfill.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    backfill.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    backfill.add_argument("--target", choices=["stock", "etf", "market-index", "all"], default="stock")
    backfill.add_argument("--max-etfs", type=int, default=None)
    backfill.set_defaults(func=cmd_backfill)

    timeseries = sub.add_parser("export-timeseries")
    timeseries.add_argument(
        "--target",
        choices=["stock", "etf", "market-index", "kfi", "validation"],
        required=True,
    )
    timeseries.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    timeseries.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    timeseries.add_argument("--ticker", action="append", help="종목코드. 쉼표 구분 또는 반복 입력 가능")
    timeseries.add_argument("--etf-ticker", action="append", help="ETF 코드. 쉼표 구분 또는 반복 입력 가능")
    timeseries.add_argument("--index-code", action="append", help="시장지수 코드. 쉼표 구분 또는 반복 입력 가능")
    timeseries.add_argument("--index-name", action="append", help="시장지수명. 예: KOSPI,KOSDAQ")
    timeseries.add_argument("--output", required=True, help="출력 CSV 경로")
    timeseries.set_defaults(func=_dispatch_export_timeseries)

    exposure = sub.add_parser("export-exposure")
    exposure.add_argument("--date", required=True, help="ETF holdings 기준일, YYYY-MM-DD")
    exposure.add_argument("--from-db", action="store_true", help="Live pykrx 수집 대신 DB 적재 데이터를 사용")
    exposure.add_argument("--max-etfs", type=int, default=None, help="빠른 테스트용 ETF 수 제한")
    exposure.add_argument("--min-ownership-ratio", type=float, default=0.0)
    exposure.add_argument("--min-etf-count", type=int, default=1)
    exposure.add_argument("--top-n", type=int, default=None)
    exposure.add_argument("--output-dir", default="data/processed/exposure")
    exposure.set_defaults(func=cmd_export_exposure)

    kfi = sub.add_parser("build-kfi")
    kfi.add_argument("--date", required=True, help="YYYY-MM-DD")
    kfi.add_argument("--lookback-days", type=int, default=40)
    kfi.add_argument("--max-etfs", type=int, default=None)
    kfi.add_argument("--output", default="data/processed/kfi_scores.parquet")
    kfi.set_defaults(func=cmd_build_kfi)

    validate = sub.add_parser("validate")
    validate.add_argument("--event-date", required=True)
    validate.add_argument("--stock-history", required=True)
    validate.add_argument("--market-history", required=True)
    validate.add_argument("--kfi-scores", required=True)
    validate.set_defaults(func=cmd_validate)
    return parser


def _dispatch_export_timeseries(args: argparse.Namespace) -> None:
    if args.ticker and args.target not in {"stock", "kfi", "validation"}:
        raise SystemExit("--ticker can only be used with stock, kfi, or validation targets.")
    if args.etf_ticker and args.target != "etf":
        raise SystemExit("--etf-ticker can only be used with the etf target.")
    if (args.index_code or args.index_name) and args.target != "market-index":
        raise SystemExit("--index-code and --index-name can only be used with the market-index target.")

    target_config = {
        "stock": {
            "date_column": "f.trade_date",
            "ticker_column": "f.ticker",
            "etf_ticker_column": "NULL",
            "order_by": "f.trade_date, f.ticker",
            "select_sql": """
                SELECT f.*, d.name AS stock_name
                FROM bitamin.fact_stock_daily f
                LEFT JOIN bitamin.dim_stock d USING (ticker)
            """,
        },
        "etf": {
            "date_column": "f.trade_date",
            "ticker_column": "NULL",
            "etf_ticker_column": "f.etf_ticker",
            "order_by": "f.trade_date, f.etf_ticker",
            "select_sql": """
                SELECT f.*, d.name AS etf_name, d.is_leveraged, d.is_inverse,
                       d.is_synthetic, d.is_foreign_underlying
                FROM bitamin.fact_etf_daily f
                LEFT JOIN bitamin.dim_etf d USING (etf_ticker)
            """,
        },
        "market-index": {
            "date_column": "trade_date",
            "ticker_column": "NULL",
            "etf_ticker_column": "NULL",
            "order_by": "trade_date, index_code",
            "select_sql": "SELECT * FROM bitamin.fact_market_index_daily",
        },
        "kfi": {
            "date_column": "score_date",
            "ticker_column": "ticker",
            "etf_ticker_column": "NULL",
            "order_by": "score_date, kfi_korea DESC, ticker",
            "select_sql": "SELECT * FROM bitamin.fact_kfi_scores",
        },
        "validation": {
            "date_column": "event_date",
            "ticker_column": "ticker",
            "etf_ticker_column": "NULL",
            "order_by": "event_date, decile, ticker",
            "select_sql": "SELECT * FROM bitamin.fact_event_validation",
        },
    }[args.target]
    for key, value in target_config.items():
        setattr(args, key, value)
    cmd_export_timeseries(args)


def main() -> None:
    load_settings()
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except KRXDataError as exc:
        print(f"KRX data collection failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
