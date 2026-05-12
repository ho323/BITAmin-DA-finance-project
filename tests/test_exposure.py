import pandas as pd

from bitamin_finance.features.exposure import (
    build_etf_constituent_tables,
    build_stock_etf_exposure,
    filter_exposure_candidates,
)


def test_build_stock_etf_exposure_outputs_summary_detail_matrix() -> None:
    stock_daily = pd.DataFrame(
        [
            {
                "trade_date": "2025-06-30",
                "ticker": "000001",
                "market": "KOSPI",
                "close": 1000,
                "market_cap": 1000000,
                "listed_shares_proxy": 1000,
            },
            {
                "trade_date": "2025-06-30",
                "ticker": "000002",
                "market": "KOSDAQ",
                "close": 2000,
                "market_cap": 2000000,
                "listed_shares_proxy": 2000,
            },
        ]
    )
    stock_universe = pd.DataFrame(
        [
            {"ticker": "000001", "name": "Alpha", "market": "KOSPI"},
            {"ticker": "000002", "name": "Beta", "market": "KOSDAQ"},
        ]
    )
    etf_universe = pd.DataFrame(
        [
            {"etf_ticker": "ETF001", "name": "반도체 ETF"},
            {"etf_ticker": "ETF002", "name": "테크 ETF"},
        ]
    )
    holdings = pd.DataFrame(
        [
            {
                "as_of_date": "2025-06-30",
                "etf_ticker": "ETF001",
                "stock_ticker": "000001",
                "shares": 100,
                "valuation_amount": 100000,
                "weight": 10,
            },
            {
                "as_of_date": "2025-06-30",
                "etf_ticker": "ETF002",
                "stock_ticker": "000001",
                "shares": 50,
                "valuation_amount": 50000,
                "weight": 5,
            },
        ]
    )

    summary, detail, matrix = build_stock_etf_exposure(
        stock_daily, holdings, stock_universe, etf_universe
    )

    alpha = summary.loc[summary["stock_ticker"] == "000001"].iloc[0]
    assert alpha["etf_ownership_ratio"] == 0.15
    assert alpha["etf_count"] == 2
    assert len(detail) == 2
    assert "반도체 ETF" in matrix.columns

    etf_summary, etf_constituents = build_etf_constituent_tables(detail)
    first_etf = etf_summary.loc[etf_summary["etf_ticker"] == "ETF001"].iloc[0]
    assert first_etf["constituent_count"] == 1
    assert first_etf["top_stock_ticker"] == "000001"
    assert set(["shares", "weight_in_etf", "shares_pct_of_stock"]).issubset(etf_constituents.columns)


def test_filter_exposure_candidates() -> None:
    summary = pd.DataFrame(
        [
            {"stock_ticker": "000001", "etf_ownership_ratio": 0.10, "etf_count": 2},
            {"stock_ticker": "000002", "etf_ownership_ratio": 0.01, "etf_count": 1},
        ]
    )
    candidates = filter_exposure_candidates(summary, min_ownership_ratio=0.05, min_etf_count=2)
    assert candidates["stock_ticker"].tolist() == ["000001"]
