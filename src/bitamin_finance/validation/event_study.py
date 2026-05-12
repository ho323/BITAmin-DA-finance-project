from __future__ import annotations

import numpy as np
import pandas as pd


def _prepare_history(stock_history: pd.DataFrame) -> pd.DataFrame:
    history = stock_history.copy()
    history["trade_date"] = pd.to_datetime(history["trade_date"])
    history["close"] = pd.to_numeric(history["close"], errors="coerce")
    return history.sort_values(["ticker", "trade_date"])


def stock_event_returns(stock_history: pd.DataFrame, event_date: str) -> pd.DataFrame:
    history = _prepare_history(stock_history)
    event_ts = pd.to_datetime(event_date)
    before = (
        history.loc[history["trade_date"] < event_ts]
        .groupby("ticker", as_index=False)
        .tail(1)[["ticker", "close"]]
        .rename(columns={"close": "pre_close"})
    )
    event = history.loc[history["trade_date"] == event_ts, ["ticker", "close"]]
    event = event.rename(columns={"close": "event_close"})
    returns = before.merge(event, on="ticker", how="inner")
    returns["stock_return"] = returns["event_close"] / returns["pre_close"] - 1
    return returns


def market_event_return(market_history: pd.DataFrame, event_date: str) -> float:
    market = market_history.copy()
    market["trade_date"] = pd.to_datetime(market["trade_date"])
    market["close"] = pd.to_numeric(market["close"], errors="coerce")
    event_ts = pd.to_datetime(event_date)
    pre = market.loc[market["trade_date"] < event_ts].sort_values("trade_date").tail(1)
    event = market.loc[market["trade_date"] == event_ts].tail(1)
    if pre.empty or event.empty:
        return 0.0
    return float(event["close"].iloc[0] / pre["close"].iloc[0] - 1)


def risk_controls(stock_history: pd.DataFrame, event_date: str) -> pd.DataFrame:
    history = _prepare_history(stock_history)
    event_ts = pd.to_datetime(event_date)
    history = history.loc[history["trade_date"] <= event_ts].copy()
    history["return"] = history.groupby("ticker")["close"].pct_change()
    trailing = history.groupby("ticker", group_keys=False).tail(21)
    controls = trailing.groupby("ticker", as_index=False).agg(
        volatility_20d=("return", "std"),
        avg_volume_20d=("volume", "mean"),
    )
    latest = history.groupby("ticker", as_index=False).tail(1)[
        ["ticker", "market_cap", "volume", "listed_shares_proxy"]
    ]
    controls = controls.merge(latest, on="ticker", how="left")
    controls["turnover"] = controls["volume"] / controls["listed_shares_proxy"].replace({0: np.nan})
    controls["beta"] = np.nan
    return controls[["ticker", "market_cap", "volatility_20d", "turnover", "beta"]]


def build_event_validation_frame(
    event_date: str,
    stock_history: pd.DataFrame,
    market_history: pd.DataFrame,
    kfi_scores: pd.DataFrame,
    index_version: str = "kfi_korea_mvp_v1",
) -> pd.DataFrame:
    returns = stock_event_returns(stock_history, event_date)
    controls = risk_controls(stock_history, event_date)
    market_return = market_event_return(market_history, event_date)
    frame = (
        returns.merge(controls, on="ticker", how="left")
        .merge(kfi_scores, on="ticker", how="inner", suffixes=("", "_score"))
    )
    frame["market_return"] = market_return
    frame["excess_drop"] = -(frame["stock_return"] - frame["market_return"])
    frame["event_date"] = event_date
    frame["index_version"] = frame.get("index_version", index_version)
    frame["decile"] = pd.qcut(
        frame["kfi_korea"].rank(method="first"),
        q=min(10, max(1, len(frame))),
        labels=False,
        duplicates="drop",
    )
    frame["decile"] = frame["decile"].fillna(0).astype(int) + 1
    frame["data_quality_flags"] = [{} for _ in range(len(frame))]
    columns = [
        "event_date",
        "ticker",
        "index_version",
        "stock_return",
        "market_return",
        "excess_drop",
        "kfi_base",
        "kfi_korea",
        "market_cap",
        "volatility_20d",
        "turnover",
        "beta",
        "decile",
        "data_quality_flags",
    ]
    return frame[columns].reset_index(drop=True)


def fit_event_regression(validation_frame: pd.DataFrame) -> pd.DataFrame:
    try:
        import statsmodels.formula.api as smf
    except ImportError as exc:
        raise RuntimeError("statsmodels is required for regression validation.") from exc

    df = validation_frame.copy()
    df["log_market_cap"] = np.log(pd.to_numeric(df["market_cap"], errors="coerce").clip(lower=1))
    df["volatility_20d"] = pd.to_numeric(df["volatility_20d"], errors="coerce").fillna(0)
    df["turnover"] = pd.to_numeric(df["turnover"], errors="coerce").fillna(0)
    formula = "excess_drop ~ kfi_korea + log_market_cap + volatility_20d + turnover"
    model = smf.ols(formula, data=df).fit(cov_type="HC3")
    return pd.DataFrame(
        {
            "term": model.params.index,
            "coef": model.params.values,
            "std_err": model.bse.values,
            "p_value": model.pvalues.values,
            "r_squared": model.rsquared,
            "nobs": int(model.nobs),
        }
    )


def decile_summary(validation_frame: pd.DataFrame) -> pd.DataFrame:
    return (
        validation_frame.groupby("decile", as_index=False)
        .agg(
            avg_excess_drop=("excess_drop", "mean"),
            avg_kfi_korea=("kfi_korea", "mean"),
            ticker_count=("ticker", "count"),
        )
        .sort_values("decile")
    )
