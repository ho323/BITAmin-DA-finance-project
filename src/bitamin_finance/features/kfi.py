from __future__ import annotations

import numpy as np
import pandas as pd


KFI_WEIGHTS = {
    "ownership_pressure": 0.30,
    "liquidity_pressure": 0.30,
    "leveraged_inverse_pressure": 0.15,
    "deviation_stress": 0.15,
    "flow_stress": 0.10,
}


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.replace({0: np.nan})
    return (numerator / denominator).replace([np.inf, -np.inf], np.nan)


def zscore(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").fillna(0.0)
    std = numeric.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(np.zeros(len(numeric)), index=numeric.index)
    return (numeric - numeric.mean()) / std


def _latest_history_window(stock_history: pd.DataFrame, score_date: str, window: int = 20) -> pd.DataFrame:
    if stock_history.empty:
        return stock_history
    history = stock_history.copy()
    history["trade_date"] = pd.to_datetime(history["trade_date"])
    cutoff = pd.to_datetime(score_date)
    history = history.loc[history["trade_date"] <= cutoff].sort_values(["ticker", "trade_date"])
    return history.groupby("ticker", group_keys=False).tail(window)


def _average_trading_value(stock_history: pd.DataFrame, score_date: str) -> pd.DataFrame:
    window = _latest_history_window(stock_history, score_date, window=20)
    if window.empty:
        return pd.DataFrame(columns=["ticker", "avg_trading_value_20d"])
    return (
        window.groupby("ticker", as_index=False)["trading_value"]
        .mean()
        .rename(columns={"trading_value": "avg_trading_value_20d"})
    )


def _flow_stress(etf_daily: pd.DataFrame, score_date: str) -> pd.DataFrame:
    if etf_daily.empty or "trading_value" not in etf_daily:
        return pd.DataFrame(columns=["etf_ticker", "flow_stress_etf"])
    df = etf_daily.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    score_ts = pd.to_datetime(score_date)
    latest = df.loc[df["trade_date"] == score_ts, ["etf_ticker", "trading_value"]].rename(
        columns={"trading_value": "latest_trading_value"}
    )
    trailing = (
        df.loc[df["trade_date"] <= score_ts]
        .sort_values(["etf_ticker", "trade_date"])
        .groupby("etf_ticker", group_keys=False)
        .tail(20)
        .groupby("etf_ticker", as_index=False)["trading_value"]
        .mean()
        .rename(columns={"trading_value": "avg_etf_trading_value_20d"})
    )
    merged = latest.merge(trailing, on="etf_ticker", how="left")
    merged["flow_stress_etf"] = safe_divide(
        merged["latest_trading_value"], merged["avg_etf_trading_value_20d"]
    ).fillna(0.0)
    return merged[["etf_ticker", "flow_stress_etf"]]


def compute_kfi_components(
    score_date: str,
    stock_daily: pd.DataFrame,
    etf_holdings: pd.DataFrame,
    etf_daily: pd.DataFrame,
    stock_history: pd.DataFrame,
) -> pd.DataFrame:
    stock = stock_daily.copy()
    stock = stock.rename(columns={"stock_ticker": "ticker"})
    if stock.empty:
        return pd.DataFrame()

    holdings = etf_holdings.copy()
    holdings = holdings.rename(columns={"ticker": "stock_ticker"})
    if holdings.empty:
        holdings = pd.DataFrame(columns=["stock_ticker", "etf_ticker", "shares", "valuation_amount"])

    etf = etf_daily.copy()
    for col in ["is_leveraged", "is_inverse"]:
        if col not in etf:
            etf[col] = False

    holdings = holdings.merge(
        etf[["etf_ticker", "deviation_rate", "is_leveraged", "is_inverse"]].drop_duplicates(
            "etf_ticker"
        ),
        on="etf_ticker",
        how="left",
    )
    holdings = holdings.merge(_flow_stress(etf_daily, score_date), on="etf_ticker", how="left")
    holdings["is_leveraged"] = holdings["is_leveraged"].fillna(False)
    holdings["is_inverse"] = holdings["is_inverse"].fillna(False)
    holdings["valuation_amount"] = pd.to_numeric(holdings.get("valuation_amount"), errors="coerce")
    holdings["shares"] = pd.to_numeric(holdings.get("shares"), errors="coerce")
    holdings["deviation_rate"] = pd.to_numeric(holdings.get("deviation_rate"), errors="coerce")
    holdings["flow_stress_etf"] = pd.to_numeric(holdings.get("flow_stress_etf"), errors="coerce")
    holdings["leveraged_inverse_amount"] = np.where(
        holdings["is_leveraged"] | holdings["is_inverse"],
        holdings["valuation_amount"].fillna(0.0),
        0.0,
    )
    holdings["deviation_weighted_amount"] = (
        holdings["valuation_amount"].fillna(0.0) * holdings["deviation_rate"].abs().fillna(0.0)
    )
    holdings["flow_weighted_amount"] = (
        holdings["valuation_amount"].fillna(0.0) * holdings["flow_stress_etf"].fillna(0.0)
    )

    exposure = (
        holdings.groupby("stock_ticker", as_index=False)
        .agg(
            etf_holding_shares=("shares", "sum"),
            etf_holding_amount=("valuation_amount", "sum"),
            leveraged_inverse_amount=("leveraged_inverse_amount", "sum"),
            deviation_weighted_amount=("deviation_weighted_amount", "sum"),
            flow_weighted_amount=("flow_weighted_amount", "sum"),
        )
        .rename(columns={"stock_ticker": "ticker"})
    )
    avg_trading = _average_trading_value(stock_history, score_date)
    base = stock.merge(exposure, on="ticker", how="left").merge(avg_trading, on="ticker", how="left")
    exposure_cols = [
        "etf_holding_shares",
        "etf_holding_amount",
        "leveraged_inverse_amount",
        "deviation_weighted_amount",
        "flow_weighted_amount",
    ]
    base[exposure_cols] = base[exposure_cols].fillna(0.0)
    base["avg_trading_value_20d"] = base["avg_trading_value_20d"].fillna(base.get("trading_value", 0))
    listed_shares = pd.to_numeric(base.get("listed_shares_proxy"), errors="coerce")
    base["ownership_pressure"] = safe_divide(base["etf_holding_shares"], listed_shares).fillna(0.0)
    base["liquidity_pressure"] = safe_divide(
        base["etf_holding_amount"], base["avg_trading_value_20d"]
    ).fillna(0.0)
    base["leveraged_inverse_pressure"] = safe_divide(
        base["leveraged_inverse_amount"], base["etf_holding_amount"]
    ).fillna(0.0)
    base["deviation_stress"] = safe_divide(
        base["deviation_weighted_amount"], base["etf_holding_amount"]
    ).fillna(0.0)
    base["flow_stress"] = safe_divide(
        base["flow_weighted_amount"], base["etf_holding_amount"]
    ).fillna(0.0)
    return base


def compute_kfi_scores(
    score_date: str,
    stock_daily: pd.DataFrame,
    etf_holdings: pd.DataFrame,
    etf_daily: pd.DataFrame,
    stock_history: pd.DataFrame,
    index_version: str = "kfi_korea_mvp_v1",
) -> pd.DataFrame:
    components = compute_kfi_components(score_date, stock_daily, etf_holdings, etf_daily, stock_history)
    if components.empty:
        return components
    components["kfi_base"] = (
        0.5 * zscore(components["ownership_pressure"])
        + 0.5 * zscore(components["liquidity_pressure"])
    )
    components["kfi_korea"] = sum(
        weight * zscore(components[column]) for column, weight in KFI_WEIGHTS.items()
    )
    components["score_date"] = score_date
    components["index_version"] = index_version
    components["data_quality_flags"] = components.apply(
        lambda row: {
            "listed_shares_proxy": bool(
                isinstance(row.get("data_quality_flags"), dict)
                and row.get("data_quality_flags", {}).get("listed_shares_proxy", False)
            ),
            "no_etf_exposure": float(row.get("etf_holding_amount", 0) or 0) == 0,
        },
        axis=1,
    )
    columns = [
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
    return components[columns].sort_values("kfi_korea", ascending=False).reset_index(drop=True)

