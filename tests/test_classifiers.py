import pandas as pd

from bitamin_finance.data.classifiers import classify_etf_name
from bitamin_finance.data.krx_client import merge_stock_ohlcv_and_cap


def test_classify_leveraged_inverse_etf_name() -> None:
    result = classify_etf_name("KODEX 200선물인버스2X")
    assert result["is_inverse"] is True
    assert result["is_leveraged"] is True


def test_classify_foreign_synthetic_etf_name() -> None:
    result = classify_etf_name("TIGER 미국나스닥100 합성")
    assert result["is_foreign_underlying"] is True
    assert result["is_synthetic"] is True


def test_merge_stock_ohlcv_and_cap_prefers_existing_market_cap_and_fills_missing() -> None:
    ohlcv = pd.DataFrame(
        {
            "open": [1000, 2000],
            "high": [1100, 2100],
            "low": [900, 1900],
            "close": [1050, 2050],
            "market_cap": [1000000, None],
        },
        index=["000001", "000002"],
    )
    cap = pd.DataFrame(
        {
            "market_cap": [999999, 2000000, 3000000],
            "listed_shares": [1000, 1000, 1000],
        },
        index=["000001", "000002", "000003"],
    )

    result = merge_stock_ohlcv_and_cap(ohlcv, cap)

    assert result.loc["000001", "market_cap"] == 1000000
    assert result.loc["000002", "market_cap"] == 2000000
    assert result.loc["000003", "listed_shares"] == 1000
