from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import text

from bitamin_finance.db.connection import get_engine
from bitamin_finance.validation.event_study import decile_summary, fit_event_regression


st.set_page_config(page_title="Korean Fragility Index", layout="wide")
st.title("Korean ETF Fragility Index")


@st.cache_data(ttl=300)
def read_sql(sql: str, params: dict[str, object] | None = None) -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as connection:
        return pd.read_sql(text(sql), connection, params=params or {})


def available_dates(table: str, column: str) -> list[str]:
    try:
        df = read_sql(
            f"SELECT DISTINCT {column} AS dt FROM bitamin.{table} ORDER BY {column} DESC LIMIT 100"
        )
    except Exception:
        return []
    return [str(value) for value in df["dt"].tolist()]


score_dates = available_dates("fact_kfi_scores", "score_date")
event_dates = available_dates("fact_event_validation", "event_date")

if not score_dates:
    st.info("No K-FI scores found yet. Run the ETL and K-FI build DAGs first.")
    st.stop()

score_date = st.sidebar.selectbox("Score date", score_dates)
event_date = st.sidebar.selectbox("Event date", event_dates or score_dates)
index_version = st.sidebar.text_input("Index version", value="kfi_korea_mvp_v1")

scores = read_sql(
    """
    SELECT s.*, d.name, d.market
    FROM bitamin.fact_kfi_scores s
    LEFT JOIN bitamin.dim_stock d USING (ticker)
    WHERE score_date = :score_date AND index_version = :index_version
    ORDER BY kfi_korea DESC
    """,
    {"score_date": score_date, "index_version": index_version},
)

top_n = st.sidebar.slider("Top N", min_value=10, max_value=100, value=30, step=10)

metric_cols = st.columns(4)
metric_cols[0].metric("Scored stocks", f"{len(scores):,}")
metric_cols[1].metric("Median K-FI Korea", f"{scores['kfi_korea'].median():.3f}")
metric_cols[2].metric("Max K-FI Korea", f"{scores['kfi_korea'].max():.3f}")
metric_cols[3].metric("ETF exposed", f"{(~scores['data_quality_flags'].astype(str).str.contains('no_etf_exposure.: true')).sum():,}")

left, right = st.columns([1.1, 1])
with left:
    st.subheader("Top Fragility Stocks")
    st.dataframe(
        scores[
            [
                "ticker",
                "name",
                "market",
                "kfi_korea",
                "kfi_base",
                "ownership_pressure",
                "liquidity_pressure",
                "leveraged_inverse_pressure",
                "deviation_stress",
                "flow_stress",
            ]
        ].head(top_n),
        use_container_width=True,
        hide_index=True,
    )

with right:
    st.subheader("Component Profile")
    component_cols = [
        "ownership_pressure",
        "liquidity_pressure",
        "leveraged_inverse_pressure",
        "deviation_stress",
        "flow_stress",
    ]
    melted = scores.head(top_n).melt(
        id_vars=["ticker"], value_vars=component_cols, var_name="component", value_name="value"
    )
    st.plotly_chart(
        px.bar(melted, x="ticker", y="value", color="component", barmode="stack"),
        use_container_width=True,
    )

validation = pd.DataFrame()
if event_dates:
    validation = read_sql(
        """
        SELECT *
        FROM bitamin.fact_event_validation
        WHERE event_date = :event_date AND index_version = :index_version
        """,
        {"event_date": event_date, "index_version": index_version},
    )

if not validation.empty:
    st.subheader("Event Validation")
    chart = px.scatter(
        validation,
        x="kfi_korea",
        y="excess_drop",
        color="decile",
        hover_data=["ticker", "stock_return", "market_return"],
        trendline="ols",
    )
    st.plotly_chart(chart, use_container_width=True)
    col_a, col_b = st.columns(2)
    with col_a:
        st.caption("Decile summary")
        st.dataframe(decile_summary(validation), use_container_width=True, hide_index=True)
    with col_b:
        st.caption("HC3 robust regression")
        try:
            st.dataframe(fit_event_regression(validation), use_container_width=True, hide_index=True)
        except Exception as exc:
            st.warning(f"Regression unavailable: {exc}")

