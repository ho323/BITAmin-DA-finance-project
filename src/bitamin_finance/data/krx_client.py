from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from bitamin_finance.data.classifiers import classify_etf_name


class KRXDataError(RuntimeError):
    """Raised when KRX/pykrx returns an unusable response."""


def _require_pykrx() -> Any:
    if not (os.getenv("KRX_ID") and os.getenv("KRX_PW")):
        raise KRXDataError(
            "KRX_ID/KRX_PW가 설정되지 않았습니다. ETF 구성종목(PDF)과 KRX 전 종목 데이터는 "
            "현재 KRX 로그인 세션이 필요합니다. .env에 KRX_ID, KRX_PW를 추가한 뒤 다시 실행하세요."
        )
    try:
        from pykrx import stock
    except ImportError as exc:
        raise RuntimeError(
            "pykrx is required for live KRX collection. Install project dependencies first."
        ) from exc
    return stock


def krx_date(value: date | datetime | str) -> str:
    if isinstance(value, str):
        return value.replace("-", "")
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime("%Y%m%d")


def iso_date(value: date | datetime | str) -> str:
    if isinstance(value, str):
        clean = value.replace("-", "")
        return f"{clean[:4]}-{clean[4:6]}-{clean[6:]}"
    if isinstance(value, datetime):
        value = value.date()
    return value.isoformat()


def normalize_krx_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {
        "시가": "open",
        "고가": "high",
        "저가": "low",
        "종가": "close",
        "거래량": "volume",
        "거래대금": "trading_value",
        "시가총액": "market_cap",
        "상장주식수": "listed_shares",
        "상장주식수(천주)": "listed_shares_thousand",
        "NAV": "nav",
        "괴리율": "deviation_rate",
        "추적오차율": "tracking_error_rate",
        "계약수": "shares",
        "금액": "valuation_amount",
        "비중": "weight",
    }
    return df.rename(columns={key: value for key, value in mapping.items() if key in df.columns})


def _assert_non_empty(df: pd.DataFrame, label: str) -> None:
    if df.empty:
        raise KRXDataError(
            f"{label} 수집 결과가 비어 있습니다. 날짜가 휴장일인지, 네트워크/KRX 접근이 가능한지, "
            "또는 KRX_ID/KRX_PW 환경 변수가 필요한지 확인하세요."
        )


def _assert_columns(df: pd.DataFrame, required: list[str], label: str) -> None:
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise KRXDataError(
            f"{label} 응답에 필요한 컬럼이 없습니다: {missing}. "
            "pykrx/KRX 응답 형식, 로그인 환경 변수, 또는 날짜를 확인하세요."
        )


def merge_stock_ohlcv_and_cap(ohlcv: pd.DataFrame, cap: pd.DataFrame) -> pd.DataFrame:
    """Merge pykrx OHLCV and market-cap frames without duplicate column crashes."""
    df = ohlcv.reindex(ohlcv.index.union(cap.index)).copy()
    for column in ["market_cap", "listed_shares"]:
        if column not in cap.columns:
            continue
        if column in df.columns:
            df[column] = df[column].combine_first(cap[column])
        else:
            df[column] = cap[column]
    return df


@dataclass
class KRXClient:
    markets: tuple[str, ...] = ("KOSPI", "KOSDAQ")
    index_codes: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.index_codes is None:
            self.index_codes = {"KOSPI": "1001", "KOSDAQ": "2001", "KOSPI200": "1028"}

    def collect_stock_universe(self, as_of_date: str) -> pd.DataFrame:
        stock = _require_pykrx()
        rows: list[dict[str, Any]] = []
        date_arg = krx_date(as_of_date)
        for market in self.markets:
            for ticker in stock.get_market_ticker_list(date_arg, market=market):
                rows.append({
                    "ticker": ticker,
                    "name": stock.get_market_ticker_name(ticker),
                    "market": market,
                    "is_active": True,
                })
        result = pd.DataFrame(rows)
        _assert_non_empty(result, f"{as_of_date} stock universe")
        return result

    def collect_stock_daily(self, trade_date: str) -> pd.DataFrame:
        stock = _require_pykrx()
        date_arg = krx_date(trade_date)
        frames: list[pd.DataFrame] = []
        for market in self.markets:
            ohlcv = normalize_krx_columns(stock.get_market_ohlcv_by_ticker(date_arg, market=market))
            cap = normalize_krx_columns(stock.get_market_cap_by_ticker(date_arg, market=market))
            if ohlcv.empty and cap.empty:
                continue
            _assert_columns(ohlcv, ["open", "high", "low", "close"], f"{trade_date} {market} OHLCV")
            df = merge_stock_ohlcv_and_cap(ohlcv, cap)
            df = df.reset_index().rename(columns={"티커": "ticker", "index": "ticker"})
            df["trade_date"] = iso_date(trade_date)
            df["market"] = market
            frames.append(df)
        if not frames:
            return pd.DataFrame()
        result = pd.concat(frames, ignore_index=True)
        result["listed_shares_proxy"] = result["listed_shares"]
        missing = result["listed_shares_proxy"].isna()
        if "market_cap" in result and "close" in result:
            proxy = result["market_cap"] / result["close"].replace({0: pd.NA})
            result.loc[missing, "listed_shares_proxy"] = proxy.loc[missing]
        result["data_quality_flags"] = result.apply(
            lambda row: {"listed_shares_proxy": pd.isna(row.get("listed_shares"))},
            axis=1,
        )
        _assert_non_empty(result, f"{trade_date} stock daily")
        return result

    def collect_etf_universe(self, as_of_date: str) -> pd.DataFrame:
        stock = _require_pykrx()
        rows: list[dict[str, Any]] = []
        for ticker in stock.get_etf_ticker_list(krx_date(as_of_date)):
            name = stock.get_etf_ticker_name(ticker)
            rows.append({"etf_ticker": ticker, "name": name, **classify_etf_name(name)})
        result = pd.DataFrame(rows)
        _assert_non_empty(result, f"{as_of_date} ETF universe")
        return result

    def collect_etf_daily(self, trade_date: str, max_etfs: int | None = None) -> pd.DataFrame:
        stock = _require_pykrx()
        date_arg = krx_date(trade_date)
        try:
            df = stock.get_etf_ohlcv_by_ticker(date_arg)
            df = normalize_krx_columns(df).reset_index().rename(
                columns={"티커": "etf_ticker", "index": "etf_ticker"}
            )
            if max_etfs:
                df = df.head(max_etfs).copy()
        except Exception:
            rows = []
            etfs = stock.get_etf_ticker_list(date_arg)
            if max_etfs:
                etfs = etfs[:max_etfs]
            for ticker in etfs:
                ohlcv = stock.get_etf_ohlcv_by_date(date_arg, date_arg, ticker)
                if ohlcv.empty:
                    continue
                row = normalize_krx_columns(ohlcv).iloc[-1].to_dict()
                row["etf_ticker"] = ticker
                rows.append(row)
            df = pd.DataFrame(rows)
        _assert_non_empty(df, f"{trade_date} ETF daily")
        df["trade_date"] = iso_date(trade_date)
        deviation_frames = []
        etf_tickers = list(df["etf_ticker"].dropna().unique())
        for index, ticker in enumerate(etf_tickers, start=1):
            if index == 1 or index % 100 == 0 or index == len(etf_tickers):
                print(f"[ETF deviation] {trade_date} {index}/{len(etf_tickers)}", flush=True)
            try:
                dev = normalize_krx_columns(stock.get_etf_price_deviation(date_arg, date_arg, ticker))
            except Exception:
                continue
            if not dev.empty:
                row = dev.iloc[-1].to_dict()
                row["etf_ticker"] = ticker
                deviation_frames.append(row)
        if deviation_frames:
            dev_df = pd.DataFrame(deviation_frames)
            df = df.merge(dev_df[["etf_ticker", "nav", "deviation_rate"]], on="etf_ticker", how="left")
        df["data_quality_flags"] = [{} for _ in range(len(df))]
        return df

    def collect_etf_holdings(self, as_of_date: str, max_etfs: int | None = None) -> pd.DataFrame:
        stock = _require_pykrx()
        date_arg = krx_date(as_of_date)
        etfs = stock.get_etf_ticker_list(date_arg)
        if max_etfs:
            etfs = etfs[:max_etfs]
        frames: list[pd.DataFrame] = []
        for index, etf_ticker in enumerate(etfs, start=1):
            if index == 1 or index % 100 == 0 or index == len(etfs):
                print(f"[ETF holdings] {as_of_date} {index}/{len(etfs)}", flush=True)
            try:
                pdf = normalize_krx_columns(
                    stock.get_etf_portfolio_deposit_file(etf_ticker, date_arg)
                )
            except Exception:
                continue
            if pdf.empty:
                continue
            pdf = pdf.reset_index().rename(columns={"티커": "stock_ticker", "index": "stock_ticker"})
            pdf["as_of_date"] = iso_date(as_of_date)
            pdf["etf_ticker"] = etf_ticker
            pdf["data_quality_flags"] = [{} for _ in range(len(pdf))]
            frames.append(pdf)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def collect_market_index_daily(self, trade_date: str) -> pd.DataFrame:
        stock = _require_pykrx()
        date_arg = krx_date(trade_date)
        rows = []
        assert self.index_codes is not None
        for index_name, index_code in self.index_codes.items():
            try:
                df = stock.get_index_ohlcv_by_date(date_arg, date_arg, index_code)
            except Exception:
                try:
                    df = stock.get_index_ohlcv(date_arg, date_arg, index_code)
                except Exception:
                    continue
            if df.empty:
                continue
            row = normalize_krx_columns(df).iloc[-1].to_dict()
            row["trade_date"] = iso_date(trade_date)
            row["index_code"] = index_code
            row["index_name"] = index_name
            rows.append(row)
        return pd.DataFrame(rows)

    def collect_recent_stock_history(self, end_date: str, lookback_days: int = 40) -> pd.DataFrame:
        end = datetime.fromisoformat(iso_date(end_date)).date()
        dates = [(end - timedelta(days=i)).isoformat() for i in range(lookback_days)]
        frames = [self.collect_stock_daily(day) for day in reversed(dates)]
        frames = [frame for frame in frames if not frame.empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
