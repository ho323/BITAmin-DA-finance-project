from __future__ import annotations

from pathlib import Path

import pandas as pd


def build_stock_etf_exposure(
    stock_daily: pd.DataFrame,
    etf_holdings: pd.DataFrame,
    stock_universe: pd.DataFrame | None = None,
    etf_universe: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build meeting-ready ETF exposure tables.

    Returns:
        summary: one row per stock, sorted by ETF ownership ratio.
        detail: one row per stock/ETF holding.
        matrix: one row per stock, ETF columns contain stock-share ownership ratios.
    """
    stock = stock_daily.copy()
    holdings = etf_holdings.copy()
    if stock.empty:
        empty = pd.DataFrame()
        return empty, empty, empty

    stock = stock.rename(columns={"stock_ticker": "ticker"})
    holdings = holdings.rename(columns={"ticker": "stock_ticker"})
    for column in ["shares", "valuation_amount", "weight"]:
        if column in holdings:
            holdings[column] = pd.to_numeric(holdings[column], errors="coerce").fillna(0.0)
    stock["listed_shares_proxy"] = pd.to_numeric(
        stock.get("listed_shares_proxy", stock.get("listed_shares")), errors="coerce"
    )
    stock["close"] = pd.to_numeric(stock.get("close"), errors="coerce")
    stock_meta_cols = ["ticker", "market", "close", "market_cap", "listed_shares_proxy"]
    stock_meta = stock[[col for col in stock_meta_cols if col in stock.columns]].drop_duplicates("ticker")
    if stock_universe is not None and not stock_universe.empty:
        universe = stock_universe.rename(columns={"stock_ticker": "ticker"}).copy()
        stock_meta = stock_meta.merge(
            universe[[c for c in ["ticker", "name"] if c in universe.columns]].drop_duplicates("ticker"),
            on="ticker",
            how="left",
        )
    if "name" not in stock_meta:
        stock_meta["name"] = stock_meta["ticker"]

    if holdings.empty:
        summary = stock_meta.assign(
            total_etf_holding_shares=0.0,
            total_etf_valuation_amount=0.0,
            etf_count=0,
            etf_ownership_ratio=0.0,
        )
        return summary, pd.DataFrame(), pd.DataFrame()

    etf_meta = pd.DataFrame()
    if etf_universe is not None and not etf_universe.empty:
        etf_meta = etf_universe.rename(columns={"ticker": "etf_ticker"}).copy()
        etf_meta = etf_meta[[c for c in ["etf_ticker", "name"] if c in etf_meta.columns]]
        etf_meta = etf_meta.rename(columns={"name": "etf_name"}).drop_duplicates("etf_ticker")
    detail = holdings.merge(stock_meta, left_on="stock_ticker", right_on="ticker", how="left")
    if not etf_meta.empty:
        detail = detail.merge(etf_meta, on="etf_ticker", how="left")
    else:
        detail["etf_name"] = detail["etf_ticker"]
    detail["stock_name"] = detail["name"].fillna(detail["stock_ticker"])
    detail["shares_pct_of_stock"] = (
        detail["shares"] / detail["listed_shares_proxy"].replace({0: pd.NA})
    ).fillna(0.0)
    detail = detail.rename(columns={"weight": "weight_in_etf"})

    summary = (
        detail.groupby("stock_ticker", as_index=False)
        .agg(
            total_etf_holding_shares=("shares", "sum"),
            total_etf_valuation_amount=("valuation_amount", "sum"),
            etf_count=("etf_ticker", "nunique"),
        )
        .merge(stock_meta, left_on="stock_ticker", right_on="ticker", how="right")
    )
    summary["stock_ticker"] = summary["stock_ticker"].fillna(summary["ticker"])
    summary["stock_name"] = summary["name"].fillna(summary["stock_ticker"])
    summary[["total_etf_holding_shares", "total_etf_valuation_amount", "etf_count"]] = summary[
        ["total_etf_holding_shares", "total_etf_valuation_amount", "etf_count"]
    ].fillna(0.0)
    summary["etf_ownership_ratio"] = (
        summary["total_etf_holding_shares"] / summary["listed_shares_proxy"].replace({0: pd.NA})
    ).fillna(0.0)
    summary = summary[
        [
            "stock_ticker",
            "stock_name",
            "market",
            "listed_shares_proxy",
            "market_cap",
            "total_etf_holding_shares",
            "etf_ownership_ratio",
            "total_etf_valuation_amount",
            "etf_count",
        ]
    ].sort_values("etf_ownership_ratio", ascending=False)

    matrix_source = detail[["stock_ticker", "stock_name", "etf_name", "shares_pct_of_stock"]].copy()
    matrix = matrix_source.pivot_table(
        index=["stock_ticker", "stock_name"],
        columns="etf_name",
        values="shares_pct_of_stock",
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()
    matrix.columns.name = None
    return summary.reset_index(drop=True), detail.reset_index(drop=True), matrix


def export_stock_etf_exposure(
    output_dir: str | Path,
    summary: pd.DataFrame,
    detail: pd.DataFrame,
    matrix: pd.DataFrame,
    prefix: str,
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": output_path / f"{prefix}_stock_etf_exposure_summary.csv",
        "detail": output_path / f"{prefix}_stock_etf_exposure_detail.csv",
        "matrix": output_path / f"{prefix}_stock_etf_exposure_matrix.csv",
    }
    summary.to_csv(paths["summary"], index=False)
    detail.to_csv(paths["detail"], index=False)
    matrix.to_csv(paths["matrix"], index=False)
    return paths


def build_etf_constituent_tables(detail: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build ETF-centric constituent detail and summary tables."""
    if detail.empty:
        return pd.DataFrame(), pd.DataFrame()

    constituents = detail.copy()
    required_defaults = {
        "etf_ticker": "",
        "etf_name": "",
        "stock_ticker": "",
        "stock_name": "",
        "market": "",
        "shares": 0.0,
        "valuation_amount": 0.0,
        "weight_in_etf": 0.0,
        "shares_pct_of_stock": 0.0,
    }
    for column, default in required_defaults.items():
        if column not in constituents:
            constituents[column] = default
    constituents["valuation_amount"] = pd.to_numeric(
        constituents["valuation_amount"], errors="coerce"
    ).fillna(0.0)
    constituents["shares"] = pd.to_numeric(constituents["shares"], errors="coerce").fillna(0.0)
    constituents["weight_in_etf"] = pd.to_numeric(
        constituents["weight_in_etf"], errors="coerce"
    ).fillna(0.0)
    constituents["shares_pct_of_stock"] = pd.to_numeric(
        constituents["shares_pct_of_stock"], errors="coerce"
    ).fillna(0.0)
    totals = constituents.groupby("etf_ticker")["valuation_amount"].transform("sum")
    constituents["valuation_weight_calc"] = (
        constituents["valuation_amount"] / totals.replace({0: pd.NA})
    ).fillna(0.0)
    constituents = constituents[
        [
            "etf_ticker",
            "etf_name",
            "stock_ticker",
            "stock_name",
            "market",
            "shares",
            "valuation_amount",
            "weight_in_etf",
            "valuation_weight_calc",
            "shares_pct_of_stock",
        ]
    ].sort_values(["etf_ticker", "weight_in_etf", "valuation_amount"], ascending=[True, False, False])

    top_rows = (
        constituents.sort_values(["etf_ticker", "weight_in_etf", "valuation_amount"], ascending=[True, False, False])
        .groupby("etf_ticker", as_index=False)
        .head(1)[["etf_ticker", "stock_ticker", "stock_name", "weight_in_etf"]]
        .rename(
            columns={
                "stock_ticker": "top_stock_ticker",
                "stock_name": "top_stock_name",
                "weight_in_etf": "top_stock_weight_in_etf",
            }
        )
    )
    summary = (
        constituents.groupby(["etf_ticker", "etf_name"], as_index=False)
        .agg(
            constituent_count=("stock_ticker", "nunique"),
            total_holding_shares=("shares", "sum"),
            total_valuation_amount=("valuation_amount", "sum"),
            max_weight_in_etf=("weight_in_etf", "max"),
        )
        .merge(top_rows, on="etf_ticker", how="left")
        .sort_values(["constituent_count", "total_valuation_amount"], ascending=[False, False])
    )
    return summary.reset_index(drop=True), constituents.reset_index(drop=True)


def export_etf_constituents(
    output_dir: str | Path,
    etf_summary: pd.DataFrame,
    etf_constituents: pd.DataFrame,
    prefix: str,
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    paths = {
        "etf_summary": output_path / f"{prefix}_etf_constituent_summary.csv",
        "etf_constituents": output_path / f"{prefix}_etf_constituents.csv",
    }
    etf_summary.to_csv(paths["etf_summary"], index=False)
    etf_constituents.to_csv(paths["etf_constituents"], index=False)
    return paths


def filter_exposure_candidates(
    summary: pd.DataFrame,
    min_ownership_ratio: float = 0.0,
    min_etf_count: int = 1,
    top_n: int | None = None,
) -> pd.DataFrame:
    if summary.empty:
        return summary.copy()
    candidates = summary.loc[
        (summary["etf_ownership_ratio"] >= min_ownership_ratio)
        & (summary["etf_count"] >= min_etf_count)
    ].copy()
    candidates = candidates.sort_values("etf_ownership_ratio", ascending=False)
    return candidates.head(top_n) if top_n else candidates
