# 데이터 명세서

본 문서는 한국형 Fragility Index(K-FI) 프로젝트에서 수집, 저장, 산출하는 데이터의 구조와 의미를 정리한다. 기준 스택은 PostgreSQL, Python ETL, Airflow, Docker, Streamlit이며, 원천 데이터는 KRX/pykrx를 통해 수집한다.

## 1. 데이터 범위

| 구분 | 내용 |
| --- | --- |
| 대상 시장 | KOSPI, KOSDAQ |
| 대상 자산 | 국내 상장 주식 전 종목, ETF, 주요 시장지수 |
| 기본 분석 기간 | 2025-01-02 ~ 2025-06-30 |
| 기준일 예시 | 2025-06-30, 2026-03-03 |
| 저장 위치 | PostgreSQL `bitamin_finance` DB의 `bitamin` schema |
| 파일 산출 위치 | `data/processed/...` |

주의: `2025-01-01`은 휴장일이고, `2025-06-31`은 존재하지 않는 날짜이므로 2025년 상반기 분석 기간은 `2025-01-02`부터 `2025-06-30`까지로 사용한다.

## 2. 원천 및 수집 방식

| 데이터 | 수집 함수/경로 | 설명 |
| --- | --- | --- |
| 종목 universe | `pykrx.stock.get_market_ticker_list`, `get_market_ticker_name` | 기준일의 KOSPI/KOSDAQ 상장 종목 목록 |
| 주식 일봉 | `get_market_ohlcv_by_ticker` | 종목별 시가, 고가, 저가, 종가, 거래량, 거래대금 등 |
| 주식 시가총액 | `get_market_cap_by_ticker` | 시가총액, 상장주식수 보완 |
| ETF universe | `get_etf_ticker_list`, `get_etf_ticker_name` | 기준일 ETF 목록과 이름 기반 분류 |
| ETF 일봉 | `get_etf_ohlcv_by_ticker` 또는 `get_etf_ohlcv_by_date` | ETF별 가격, 거래량, 거래대금 |
| ETF 괴리율/NAV | `get_etf_price_deviation` | ETF별 NAV, 괴리율 |
| ETF 구성종목 PDF | `get_etf_portfolio_deposit_file` | ETF 구성종목, 보유수량, 평가금액, 비중 |
| 시장지수 | `get_index_ohlcv_by_date` | KOSPI, KOSDAQ, KOSPI200 지수 일봉 |

ETF 구성종목 PDF 수집은 KRX 로그인 세션이 필요하므로 `.env`에 `KRX_ID`, `KRX_PW`를 설정한다.

## 3. DB 공통 규칙

| 항목 | 규칙 |
| --- | --- |
| DB명 | `bitamin_finance` |
| Schema | `bitamin` |
| 파티션 기준 | 일자 컬럼 기준 yearly range partition |
| 중복 처리 | `ON CONFLICT ... DO UPDATE` upsert |
| 재실행 정책 | 같은 날짜를 다시 실행해도 primary key 기준으로 덮어쓰기 |
| 품질 플래그 | `data_quality_flags` JSONB 컬럼에 proxy/결측 여부 기록 |
| 실행 로그 | `etl_run_log`, `data_quality_check`에 적재 이력 기록 |

## 4. DB 테이블 명세

### 4.1 `dim_stock`

종목 마스터 테이블이다.

| 컬럼 | 타입 | 키 | 설명 |
| --- | --- | --- | --- |
| `ticker` | TEXT | PK | 종목코드 |
| `name` | TEXT |  | 종목명 |
| `market` | TEXT |  | 시장 구분: KOSPI, KOSDAQ |
| `is_active` | BOOLEAN |  | 상장 활성 여부 |
| `listed_at` | DATE |  | 상장일, 현재 자동 수집 미구현 |
| `delisted_at` | DATE |  | 상폐일, 현재 자동 수집 미구현 |
| `updated_at` | TIMESTAMPTZ |  | 마지막 갱신 시각 |

### 4.2 `dim_etf`

ETF 마스터 및 ETF 유형 분류 테이블이다.

| 컬럼 | 타입 | 키 | 설명 |
| --- | --- | --- | --- |
| `etf_ticker` | TEXT | PK | ETF 종목코드 |
| `name` | TEXT |  | ETF명 |
| `issuer` | TEXT |  | 운용사, 현재 이름 기반 자동 분류 확장 예정 |
| `asset_class` | TEXT |  | 자산군, 현재 이름 기반 자동 분류 확장 예정 |
| `is_leveraged` | BOOLEAN |  | 레버리지 ETF 여부 |
| `is_inverse` | BOOLEAN |  | 인버스 ETF 여부 |
| `is_synthetic` | BOOLEAN |  | 합성 ETF 여부 |
| `is_foreign_underlying` | BOOLEAN |  | 해외 기초자산 ETF 여부 |
| `updated_at` | TIMESTAMPTZ |  | 마지막 갱신 시각 |

### 4.3 `fact_stock_daily`

전 종목 일봉 fact table이다.

| 컬럼 | 타입 | 키 | 설명 |
| --- | --- | --- | --- |
| `trade_date` | DATE | PK | 거래일 |
| `ticker` | TEXT | PK | 종목코드 |
| `market` | TEXT |  | 시장 구분 |
| `open` | NUMERIC |  | 시가 |
| `high` | NUMERIC |  | 고가 |
| `low` | NUMERIC |  | 저가 |
| `close` | NUMERIC |  | 종가 |
| `volume` | NUMERIC |  | 거래량 |
| `trading_value` | NUMERIC |  | 거래대금 |
| `market_cap` | NUMERIC |  | 시가총액 |
| `listed_shares` | NUMERIC |  | 상장주식수 |
| `listed_shares_proxy` | NUMERIC |  | K-FI 계산용 주식수. `listed_shares` 결측 시 `market_cap / close` |
| `data_quality_flags` | JSONB |  | proxy 사용 여부 등 품질 플래그 |
| `created_at` | TIMESTAMPTZ |  | 최초 적재 시각 |
| `updated_at` | TIMESTAMPTZ |  | 마지막 갱신 시각 |

### 4.4 `fact_etf_daily`

ETF 일봉 및 괴리율 fact table이다.

| 컬럼 | 타입 | 키 | 설명 |
| --- | --- | --- | --- |
| `trade_date` | DATE | PK | 거래일 |
| `etf_ticker` | TEXT | PK | ETF 종목코드 |
| `open` | NUMERIC |  | 시가 |
| `high` | NUMERIC |  | 고가 |
| `low` | NUMERIC |  | 저가 |
| `close` | NUMERIC |  | 종가 |
| `volume` | NUMERIC |  | 거래량 |
| `trading_value` | NUMERIC |  | 거래대금 |
| `nav` | NUMERIC |  | 순자산가치 |
| `deviation_rate` | NUMERIC |  | 괴리율 |
| `tracking_error_rate` | NUMERIC |  | 추적오차율. 응답에 없으면 결측 |
| `data_quality_flags` | JSONB |  | 품질 플래그 |
| `created_at` | TIMESTAMPTZ |  | 최초 적재 시각 |
| `updated_at` | TIMESTAMPTZ |  | 마지막 갱신 시각 |

### 4.5 `fact_etf_holdings`

ETF 구성종목 PDF를 저장하는 핵심 테이블이다.

| 컬럼 | 타입 | 키 | 설명 |
| --- | --- | --- | --- |
| `as_of_date` | DATE | PK | ETF PDF 기준일 |
| `etf_ticker` | TEXT | PK | ETF 종목코드 |
| `stock_ticker` | TEXT | PK | 구성종목 코드 |
| `shares` | NUMERIC |  | ETF가 보유한 해당 종목 주식 수 |
| `valuation_amount` | NUMERIC |  | 해당 구성종목 평가금액 |
| `weight` | NUMERIC |  | ETF 내 구성비중 |
| `data_quality_flags` | JSONB |  | 품질 플래그 |
| `created_at` | TIMESTAMPTZ |  | 최초 적재 시각 |
| `updated_at` | TIMESTAMPTZ |  | 마지막 갱신 시각 |

### 4.6 `fact_market_index_daily`

시장지수 일봉 테이블이다.

| 컬럼 | 타입 | 키 | 설명 |
| --- | --- | --- | --- |
| `trade_date` | DATE | PK | 거래일 |
| `index_code` | TEXT | PK | 지수코드 |
| `index_name` | TEXT |  | 지수명: KOSPI, KOSDAQ, KOSPI200 |
| `open` | NUMERIC |  | 시가 |
| `high` | NUMERIC |  | 고가 |
| `low` | NUMERIC |  | 저가 |
| `close` | NUMERIC |  | 종가 |
| `volume` | NUMERIC |  | 거래량 |
| `trading_value` | NUMERIC |  | 거래대금 |
| `market_cap` | NUMERIC |  | 시가총액 |
| `created_at` | TIMESTAMPTZ |  | 최초 적재 시각 |
| `updated_at` | TIMESTAMPTZ |  | 마지막 갱신 시각 |

### 4.7 `fact_kfi_scores`

K-FI 산출 결과 테이블이다.

| 컬럼 | 타입 | 키 | 설명 |
| --- | --- | --- | --- |
| `score_date` | DATE | PK | K-FI 산출 기준일 |
| `ticker` | TEXT | PK | 종목코드 |
| `index_version` | TEXT | PK | 지수 버전. 기본값 `kfi_korea_mvp_v1` |
| `ownership_pressure` | NUMERIC |  | ETF 보유 주식수 / 상장주식수 proxy |
| `liquidity_pressure` | NUMERIC |  | ETF 보유 평가액 / 최근 20거래일 평균 거래대금 |
| `leveraged_inverse_pressure` | NUMERIC |  | ETF 보유 평가액 중 레버리지/인버스 ETF 노출 비중 |
| `deviation_stress` | NUMERIC |  | ETF 괴리율 절대값 가중 노출 |
| `flow_stress` | NUMERIC |  | ETF 거래대금 급증 proxy 가중 노출 |
| `kfi_base` | NUMERIC |  | Base Fragility Index |
| `kfi_korea` | NUMERIC |  | 한국형 Fragility Index |
| `data_quality_flags` | JSONB |  | proxy 사용, ETF 미보유 여부 등 |
| `created_at` | TIMESTAMPTZ |  | 최초 적재 시각 |
| `updated_at` | TIMESTAMPTZ |  | 마지막 갱신 시각 |

### 4.8 `fact_event_validation`

이벤트 검증용 결과 테이블이다.

| 컬럼 | 타입 | 키 | 설명 |
| --- | --- | --- | --- |
| `event_date` | DATE | PK | 이벤트일 |
| `ticker` | TEXT | PK | 종목코드 |
| `index_version` | TEXT | PK | K-FI 버전 |
| `stock_return` | NUMERIC |  | 이벤트일 종목 수익률 |
| `market_return` | NUMERIC |  | 이벤트일 시장 수익률 |
| `excess_drop` | NUMERIC |  | 초과 하락률. `-(stock_return - market_return)` |
| `kfi_base` | NUMERIC |  | Base K-FI |
| `kfi_korea` | NUMERIC |  | Korean K-FI |
| `market_cap` | NUMERIC |  | 시가총액 통제변수 |
| `volatility_20d` | NUMERIC |  | 최근 20거래일 변동성 |
| `turnover` | NUMERIC |  | 회전율. `volume / listed_shares_proxy` |
| `beta` | NUMERIC |  | 베타. 현재 MVP에서는 결측 |
| `decile` | INTEGER |  | K-FI 순위 기반 10분위 |
| `data_quality_flags` | JSONB |  | 품질 플래그 |
| `created_at` | TIMESTAMPTZ |  | 최초 적재 시각 |
| `updated_at` | TIMESTAMPTZ |  | 마지막 갱신 시각 |

### 4.9 `etl_run_log`

ETL 실행 이력 테이블이다.

| 컬럼 | 타입 | 키 | 설명 |
| --- | --- | --- | --- |
| `run_id` | BIGSERIAL | PK | 실행 ID |
| `job_name` | TEXT |  | 작업명 |
| `started_at` | TIMESTAMPTZ |  | 시작 시각 |
| `finished_at` | TIMESTAMPTZ |  | 종료 시각 |
| `status` | TEXT |  | running, success, failed |
| `row_count` | INTEGER |  | 처리 row 수 |
| `parameters` | JSONB |  | 실행 파라미터 |
| `message` | TEXT |  | 오류 메시지 또는 부가 설명 |

### 4.10 `data_quality_check`

데이터 품질검사 결과 테이블이다.

| 컬럼 | 타입 | 키 | 설명 |
| --- | --- | --- | --- |
| `check_id` | BIGSERIAL | PK | 검사 ID |
| `run_id` | BIGINT | FK | `etl_run_log.run_id` |
| `check_name` | TEXT |  | 검사명 |
| `checked_at` | TIMESTAMPTZ |  | 검사 시각 |
| `status` | TEXT |  | pass, warn, fail |
| `observed_value` | NUMERIC |  | 관측값 |
| `threshold` | NUMERIC |  | 기준값 |
| `details` | JSONB |  | 상세 정보 |

## 5. CSV 산출물 명세

`export-exposure` 명령은 DB 또는 live KRX 수집 데이터를 사용해 회의/분석용 CSV를 생성한다.

```bash
.venv/bin/bitamin-finance export-exposure \
  --date 2025-06-30 \
  --from-db \
  --output-dir data/processed/exposure_20250630
```

### 5.1 `*_stock_etf_exposure_summary.csv`

종목별 ETF 편입 노출 요약 파일이다.

| 컬럼 | 설명 |
| --- | --- |
| `stock_ticker` | 종목코드 |
| `stock_name` | 종목명 |
| `market` | 시장 구분 |
| `listed_shares_proxy` | 상장주식수 proxy |
| `market_cap` | 시가총액 |
| `total_etf_holding_shares` | 모든 ETF가 보유한 해당 종목 주식 수 합계 |
| `etf_ownership_ratio` | `total_etf_holding_shares / listed_shares_proxy` |
| `total_etf_valuation_amount` | 모든 ETF의 해당 종목 평가금액 합계 |
| `etf_count` | 해당 종목을 보유한 ETF 수 |

### 5.2 `*_stock_etf_exposure_detail.csv`

종목-ETF 단위 상세 노출 파일이다.

| 컬럼 | 설명 |
| --- | --- |
| `as_of_date` | ETF 구성종목 기준일 |
| `etf_ticker` | ETF 종목코드 |
| `stock_ticker` | 구성종목 코드 |
| `shares` | ETF가 보유한 구성종목 주식 수 |
| `valuation_amount` | 평가금액 |
| `weight_in_etf` | ETF 내 비중 |
| `ticker` | 주식 종목코드. 내부 merge 결과 |
| `market` | 시장 구분 |
| `close` | 종가 |
| `market_cap` | 시가총액 |
| `listed_shares_proxy` | 상장주식수 proxy |
| `name` | 종목명 |
| `etf_name` | ETF명 |
| `stock_name` | 종목명 |
| `shares_pct_of_stock` | `shares / listed_shares_proxy` |

### 5.3 `*_stock_etf_exposure_matrix.csv`

종목별 ETF 편입 비율을 wide matrix로 변환한 파일이다.

| 컬럼 | 설명 |
| --- | --- |
| `stock_ticker` | 종목코드 |
| `stock_name` | 종목명 |
| ETF명 컬럼들 | 각 ETF가 해당 종목 상장주식수 proxy 대비 보유한 비율 |

### 5.4 `*_etf_constituent_summary.csv`

ETF 기준 구성종목 요약 파일이다.

| 컬럼 | 설명 |
| --- | --- |
| `etf_ticker` | ETF 종목코드 |
| `etf_name` | ETF명 |
| `constituent_count` | ETF 구성종목 수 |
| `total_holding_shares` | 구성종목 보유 주식 수 합계 |
| `total_valuation_amount` | ETF 구성종목 평가금액 합계 |
| `max_weight_in_etf` | ETF 내 최대 구성비중 |
| `top_stock_ticker` | ETF 내 최대 비중 구성종목 코드 |
| `top_stock_name` | ETF 내 최대 비중 구성종목명 |
| `top_stock_weight_in_etf` | 최대 비중 구성종목의 ETF 내 비중 |

### 5.5 `*_etf_constituents.csv`

ETF별 구성종목 상세 파일이다.

| 컬럼 | 설명 |
| --- | --- |
| `etf_ticker` | ETF 종목코드 |
| `etf_name` | ETF명 |
| `stock_ticker` | 구성종목 코드 |
| `stock_name` | 구성종목명 |
| `market` | 시장 구분 |
| `shares` | ETF 보유 주식 수 |
| `valuation_amount` | 구성종목 평가금액 |
| `weight_in_etf` | KRX PDF 기준 ETF 내 비중 |
| `valuation_weight_calc` | 평가금액 합계 기준 재계산 비중 |
| `shares_pct_of_stock` | 해당 ETF 보유수량 / 종목 상장주식수 proxy |

### 5.6 `*_candidate_stocks.csv`

ETF 편입 노출 기준 후보 종목 파일이다. 컬럼은 `*_stock_etf_exposure_summary.csv`와 동일하며, `--min-ownership-ratio`, `--min-etf-count`, `--top-n` 조건을 적용한 결과이다.

## 6. K-FI 계산 명세

### 6.1 구성요소

| 지표 | 정의 | 의미 |
| --- | --- | --- |
| `ownership_pressure` | ETF 보유 주식수 / 상장주식수 proxy | ETF가 종목 전체 주식에서 차지하는 비중 |
| `liquidity_pressure` | ETF 보유 평가액 / 최근 20거래일 평균 거래대금 | ETF 보유분이 평소 유동성 대비 얼마나 큰지 |
| `leveraged_inverse_pressure` | 레버리지/인버스 ETF 평가액 / 전체 ETF 보유 평가액 | 구조적으로 매매 압력이 커질 수 있는 ETF 노출 |
| `deviation_stress` | 괴리율 절대값 가중 ETF 노출 | ETF 가격/NAV 괴리가 큰 ETF 노출 |
| `flow_stress` | ETF 거래대금 급증 proxy 가중 ETF 노출 | ETF 거래 충격 노출 |

### 6.2 산식

`K-FI Base`:

```text
0.50 * z(ownership_pressure)
+ 0.50 * z(liquidity_pressure)
```

`K-FI Korea`:

```text
0.30 * z(ownership_pressure)
+ 0.30 * z(liquidity_pressure)
+ 0.15 * z(leveraged_inverse_pressure)
+ 0.15 * z(deviation_stress)
+ 0.10 * z(flow_stress)
```

여기서 `z(x)`는 동일 기준일의 종목 단면 z-score이다.

## 7. 검증 데이터 명세

이벤트 검증에서는 `fact_event_validation` 또는 CSV/HTML 리포트로 다음 값을 생성한다.

| 항목 | 정의 |
| --- | --- |
| `stock_return` | 이벤트일 종가 / 직전 거래일 종가 - 1 |
| `market_return` | 시장지수 이벤트일 종가 / 직전 거래일 종가 - 1 |
| `excess_drop` | `-(stock_return - market_return)` |
| `volatility_20d` | 최근 20거래일 종목 수익률 표준편차 |
| `turnover` | 거래량 / 상장주식수 proxy |
| `decile` | K-FI Korea 순위 기반 10분위 |

기본 회귀식은 다음과 같다.

```text
excess_drop ~ kfi_korea + log(market_cap) + volatility_20d + turnover
```

회귀 표준오차는 HC3 robust standard error를 사용한다.

## 8. 실행 명령 예시

2025년 상반기 주식 일봉:

```bash
.venv/bin/bitamin-finance backfill \
  --start-date 2025-01-02 \
  --end-date 2025-06-30 \
  --target stock
```

2025년 상반기 시장지수:

```bash
.venv/bin/bitamin-finance backfill \
  --start-date 2025-01-02 \
  --end-date 2025-06-30 \
  --target market-index
```

2025년 6월 30일 ETF 일봉 및 구성종목:

```bash
.venv/bin/bitamin-finance ingest \
  --date 2025-06-30 \
  --target etf
```

빠른 샘플 수집:

```bash
.venv/bin/bitamin-finance ingest \
  --date 2025-06-30 \
  --target etf \
  --max-etfs 20
```

DB에서 회의용 CSV 산출:

```bash
.venv/bin/bitamin-finance export-exposure \
  --date 2025-06-30 \
  --from-db \
  --output-dir data/processed/exposure_20250630
```

기간별 시계열 CSV 산출:

```bash
.venv/bin/bitamin-finance export-timeseries \
  --target stock \
  --start-date 2025-01-02 \
  --end-date 2025-06-30 \
  --output data/processed/timeseries/stock_2025_h1.csv
```

지원 target:

| target | DB table | 날짜 컬럼 | 주요 필터 |
| --- | --- | --- | --- |
| `stock` | `fact_stock_daily` | `trade_date` | `--ticker` |
| `etf` | `fact_etf_daily` | `trade_date` | `--etf-ticker` |
| `market-index` | `fact_market_index_daily` | `trade_date` | `--index-code`, `--index-name` |
| `kfi` | `fact_kfi_scores` | `score_date` | `--ticker` |
| `validation` | `fact_event_validation` | `event_date` | `--ticker` |

필터는 쉼표 구분 또는 반복 입력을 지원한다.

```bash
.venv/bin/bitamin-finance export-timeseries \
  --target stock \
  --start-date 2025-01-02 \
  --end-date 2025-06-30 \
  --ticker 005930,000660 \
  --output data/processed/timeseries/semiconductor_2025_h1.csv
```

## 9. 한계 및 보완 예정

| 항목 | 현재 처리 | 보완 방향 |
| --- | --- | --- |
| 유동주식수 | `market_cap / close` 또는 상장주식수 proxy | 수동 CSV 또는 외부 데이터로 free-float shares 반영 |
| ETF holdings 기간 | 기준일 스냅샷 우선 | 월말/이벤트일/일별 PDF 백필 확장 |
| ETF 운용사/자산군 | ETF명 기반 일부 분류 | 운용사 및 테마 분류 룰 고도화 |
| beta | MVP에서는 결측 | 시장수익률 대비 rolling beta 계산 |
| ETF 수집 속도 | pykrx 순차 호출 | ETF별 checkpoint 저장 또는 병렬 수집 |
