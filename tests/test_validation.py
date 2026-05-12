import pandas as pd

from bitamin_finance.validation.event_study import (
    build_event_validation_frame,
    decile_summary,
    stock_event_returns,
)


def _stock_history() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2026-03-02", "ticker": "000001", "close": 100, "market_cap": 1000, "volume": 10, "listed_shares_proxy": 100},
            {"trade_date": "2026-03-03", "ticker": "000001", "close": 90, "market_cap": 900, "volume": 20, "listed_shares_proxy": 100},
            {"trade_date": "2026-03-02", "ticker": "000002", "close": 100, "market_cap": 1000, "volume": 10, "listed_shares_proxy": 100},
            {"trade_date": "2026-03-03", "ticker": "000002", "close": 99, "market_cap": 990, "volume": 20, "listed_shares_proxy": 100},
        ]
    )


def test_stock_event_returns() -> None:
    returns = stock_event_returns(_stock_history(), "2026-03-03")
    first = returns.loc[returns["ticker"] == "000001", "stock_return"].iloc[0]
    assert round(first, 4) == -0.1


def test_build_event_validation_frame_and_deciles() -> None:
    market_history = pd.DataFrame(
        [
            {"trade_date": "2026-03-02", "close": 100},
            {"trade_date": "2026-03-03", "close": 98},
        ]
    )
    kfi_scores = pd.DataFrame(
        [
            {"ticker": "000001", "index_version": "kfi_korea_mvp_v1", "kfi_base": 1.0, "kfi_korea": 2.0},
            {"ticker": "000002", "index_version": "kfi_korea_mvp_v1", "kfi_base": -1.0, "kfi_korea": -2.0},
        ]
    )
    frame = build_event_validation_frame(
        "2026-03-03", _stock_history(), market_history, kfi_scores
    )
    assert len(frame) == 2
    assert frame["excess_drop"].notna().all()
    summary = decile_summary(frame)
    assert summary["ticker_count"].sum() == 2

