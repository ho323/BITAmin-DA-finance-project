from decimal import Decimal

import pandas as pd

from bitamin_finance.features.kfi import compute_kfi_scores, zscore


def test_zscore_constant_returns_zero() -> None:
    result = zscore(pd.Series([1, 1, 1]))
    assert result.tolist() == [0, 0, 0]


def test_compute_kfi_scores_handles_zero_liquidity_and_missing_etf() -> None:
    stock_daily = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-03",
                "ticker": "000001",
                "market": "KOSPI",
                "close": 1000,
                "trading_value": 0,
                "market_cap": 1000000,
                "listed_shares_proxy": 1000,
                "data_quality_flags": {},
            },
            {
                "trade_date": "2026-03-03",
                "ticker": "000002",
                "market": "KOSPI",
                "close": 2000,
                "trading_value": 100000,
                "market_cap": 2000000,
                "listed_shares_proxy": 1000,
                "data_quality_flags": {},
            },
        ]
    )
    stock_history = pd.concat([stock_daily.assign(trade_date="2026-03-02"), stock_daily])
    etf_holdings = pd.DataFrame(
        [
            {
                "as_of_date": "2026-03-03",
                "etf_ticker": "ETF001",
                "stock_ticker": "000001",
                "shares": 100,
                "valuation_amount": 100000,
                "weight": 10,
            }
        ]
    )
    etf_daily = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-03",
                "etf_ticker": "ETF001",
                "trading_value": 1000000,
                "deviation_rate": 0.5,
                "is_leveraged": True,
                "is_inverse": False,
            }
        ]
    )
    scores = compute_kfi_scores("2026-03-03", stock_daily, etf_holdings, etf_daily, stock_history)
    assert set(scores["ticker"]) == {"000001", "000002"}
    assert scores["kfi_korea"].notna().all()
    exposed = scores.loc[scores["ticker"] == "000001"].iloc[0]
    assert exposed["ownership_pressure"] == 0.1


def test_compute_kfi_scores_accepts_db_decimal_values() -> None:
    stock_daily = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-03",
                "ticker": "000001",
                "market": "KOSPI",
                "close": Decimal("1000"),
                "trading_value": Decimal("100000"),
                "market_cap": Decimal("1000000"),
                "listed_shares_proxy": Decimal("1000"),
                "data_quality_flags": {},
            },
        ]
    )
    stock_history = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-02",
                "ticker": "000001",
                "close": Decimal("990"),
                "trading_value": Decimal("90000"),
                "volume": Decimal("1000"),
                "market_cap": Decimal("990000"),
                "listed_shares_proxy": Decimal("1000"),
            },
            {
                "trade_date": "2026-03-03",
                "ticker": "000001",
                "close": Decimal("1000"),
                "trading_value": Decimal("100000"),
                "volume": Decimal("1000"),
                "market_cap": Decimal("1000000"),
                "listed_shares_proxy": Decimal("1000"),
            },
        ]
    )
    etf_holdings = pd.DataFrame(
        [
            {
                "as_of_date": "2026-03-03",
                "etf_ticker": "ETF001",
                "stock_ticker": "000001",
                "shares": Decimal("100"),
                "valuation_amount": Decimal("100000"),
                "weight": Decimal("10"),
            }
        ]
    )
    etf_daily = pd.DataFrame(
        [
            {
                "trade_date": "2026-03-02",
                "etf_ticker": "ETF001",
                "trading_value": Decimal("800000"),
                "deviation_rate": Decimal("0.1"),
                "is_leveraged": False,
                "is_inverse": False,
            },
            {
                "trade_date": "2026-03-03",
                "etf_ticker": "ETF001",
                "trading_value": Decimal("1000000"),
                "deviation_rate": Decimal("0.2"),
                "is_leveraged": False,
                "is_inverse": False,
            },
        ]
    )

    scores = compute_kfi_scores("2026-03-03", stock_daily, etf_holdings, etf_daily, stock_history)

    assert len(scores) == 1
    assert scores["kfi_korea"].notna().all()
    assert scores.loc[0, "ownership_pressure"] == 0.1
