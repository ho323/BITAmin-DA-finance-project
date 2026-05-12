CREATE SCHEMA IF NOT EXISTS bitamin;
SET search_path TO bitamin, public;

CREATE TABLE IF NOT EXISTS dim_stock (
    ticker TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    market TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    listed_at DATE,
    delisted_at DATE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dim_etf (
    etf_ticker TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    issuer TEXT,
    asset_class TEXT,
    is_leveraged BOOLEAN NOT NULL DEFAULT FALSE,
    is_inverse BOOLEAN NOT NULL DEFAULT FALSE,
    is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,
    is_foreign_underlying BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fact_stock_daily (
    trade_date DATE NOT NULL,
    ticker TEXT NOT NULL,
    market TEXT NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume NUMERIC,
    trading_value NUMERIC,
    market_cap NUMERIC,
    listed_shares NUMERIC,
    listed_shares_proxy NUMERIC,
    data_quality_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, ticker)
) PARTITION BY RANGE (trade_date);

CREATE TABLE IF NOT EXISTS fact_etf_daily (
    trade_date DATE NOT NULL,
    etf_ticker TEXT NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume NUMERIC,
    trading_value NUMERIC,
    nav NUMERIC,
    deviation_rate NUMERIC,
    tracking_error_rate NUMERIC,
    data_quality_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, etf_ticker)
) PARTITION BY RANGE (trade_date);

CREATE TABLE IF NOT EXISTS fact_etf_holdings (
    as_of_date DATE NOT NULL,
    etf_ticker TEXT NOT NULL,
    stock_ticker TEXT NOT NULL,
    shares NUMERIC,
    valuation_amount NUMERIC,
    weight NUMERIC,
    data_quality_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of_date, etf_ticker, stock_ticker)
) PARTITION BY RANGE (as_of_date);

CREATE TABLE IF NOT EXISTS fact_market_index_daily (
    trade_date DATE NOT NULL,
    index_code TEXT NOT NULL,
    index_name TEXT NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume NUMERIC,
    trading_value NUMERIC,
    market_cap NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, index_code)
) PARTITION BY RANGE (trade_date);

CREATE TABLE IF NOT EXISTS fact_kfi_scores (
    score_date DATE NOT NULL,
    ticker TEXT NOT NULL,
    index_version TEXT NOT NULL,
    ownership_pressure NUMERIC,
    liquidity_pressure NUMERIC,
    leveraged_inverse_pressure NUMERIC,
    deviation_stress NUMERIC,
    flow_stress NUMERIC,
    kfi_base NUMERIC,
    kfi_korea NUMERIC,
    data_quality_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (score_date, ticker, index_version)
) PARTITION BY RANGE (score_date);

CREATE TABLE IF NOT EXISTS fact_event_validation (
    event_date DATE NOT NULL,
    ticker TEXT NOT NULL,
    index_version TEXT NOT NULL,
    stock_return NUMERIC,
    market_return NUMERIC,
    excess_drop NUMERIC,
    kfi_base NUMERIC,
    kfi_korea NUMERIC,
    market_cap NUMERIC,
    volatility_20d NUMERIC,
    turnover NUMERIC,
    beta NUMERIC,
    decile INTEGER,
    data_quality_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (event_date, ticker, index_version)
) PARTITION BY RANGE (event_date);

CREATE TABLE IF NOT EXISTS etl_run_log (
    run_id BIGSERIAL PRIMARY KEY,
    job_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running',
    row_count INTEGER,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    message TEXT
);

CREATE TABLE IF NOT EXISTS data_quality_check (
    check_id BIGSERIAL PRIMARY KEY,
    run_id BIGINT REFERENCES etl_run_log(run_id),
    check_name TEXT NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL,
    observed_value NUMERIC,
    threshold NUMERIC,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE OR REPLACE FUNCTION ensure_year_partition(parent_table TEXT, year_start INTEGER)
RETURNS VOID AS $$
DECLARE
    partition_name TEXT;
    from_date DATE;
    to_date DATE;
BEGIN
    partition_name := format('%s_%s', parent_table, year_start);
    from_date := make_date(year_start, 1, 1);
    to_date := make_date(year_start + 1, 1, 1);
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS bitamin.%I PARTITION OF bitamin.%I FOR VALUES FROM (%L) TO (%L)',
        partition_name,
        parent_table,
        from_date,
        to_date
    );
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
    y INTEGER;
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'fact_stock_daily',
        'fact_etf_daily',
        'fact_etf_holdings',
        'fact_market_index_daily',
        'fact_kfi_scores',
        'fact_event_validation'
    ]
    LOOP
        FOR y IN 2010..2030 LOOP
            PERFORM ensure_year_partition(tbl, y);
        END LOOP;
    END LOOP;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_stock_daily_ticker_date ON fact_stock_daily (ticker, trade_date);
CREATE INDEX IF NOT EXISTS idx_stock_daily_date ON fact_stock_daily (trade_date);
CREATE INDEX IF NOT EXISTS idx_etf_daily_ticker_date ON fact_etf_daily (etf_ticker, trade_date);
CREATE INDEX IF NOT EXISTS idx_holdings_stock_date ON fact_etf_holdings (stock_ticker, as_of_date);
CREATE INDEX IF NOT EXISTS idx_kfi_korea_date ON fact_kfi_scores (score_date, kfi_korea DESC);
CREATE INDEX IF NOT EXISTS idx_event_validation_event ON fact_event_validation (event_date, index_version, decile);

