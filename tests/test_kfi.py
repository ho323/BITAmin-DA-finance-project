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

