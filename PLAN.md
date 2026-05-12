# 한국형 Fragility Index + 전 종목 DB/ETL 개발 계획

## Summary
- 한국 주식 전 종목 일봉 데이터베이스를 먼저 구축하고, 그 위에서 `K-FI: Korean Fragility Index` 개발과 검증을 수행한다.
- 스택은 `PostgreSQL + Python ETL + Airflow + Docker + Streamlit`으로 고정한다.
- Airflow/Docker는 로컬 MVP 기준으로 구성한다. Airflow 공식 Docker Compose는 빠른 시작용이며 운영용 한계가 있으므로, 이번 프로젝트에서는 재현 가능한 개발/시연 환경으로 사용한다: [Airflow Docker docs](https://airflow.apache.org/docs/apache-airflow/stable/howto/docker-compose/index.html).

## Architecture
- Docker services:
  - `postgres`: 분석 DB
  - `airflow-webserver`, `airflow-scheduler`, `airflow-init`: ETL 오케스트레이션
  - `streamlit`: K-FI 대시보드
  - optional `pgadmin`: DB 확인용
- Python package:
  - `src/bitamin_finance/data`: pykrx/KRX 수집기
  - `src/bitamin_finance/etl`: 정규화, upsert, 품질검사
  - `src/bitamin_finance/features`: K-FI 구성요소 계산
  - `src/bitamin_finance/validation`: 이벤트 검증, 회귀, decile test
  - `src/bitamin_finance/reporting`: 차트/표/리포트 산출
- Airflow DAGs:
  - `dag_stock_daily_ingest`: 전 종목 OHLCV/거래대금/시총 적재
  - `dag_etf_daily_ingest`: ETF 가격, NAV, 괴리율, PDF 구성종목 적재
  - `dag_kfi_build`: K-FI 산출
  - `dag_kfi_validation`: 이벤트 검증 결과 생성
  - 기본 스케줄은 KRX 장마감 이후 `Asia/Seoul 19:00` 일 1회, 백필은 CLI 파라미터로 수행한다.

## Database Design
- PostgreSQL을 사용하고, 시계열 fact table은 `trade_date` 기준 yearly range partition으로 설계한다. PostgreSQL partitioning은 공식 문서의 range partition 방식을 따른다: [PostgreSQL partitioning](https://www.postgresql.org/docs/17/ddl-partitioning.html).
- Core tables:
  - `dim_stock`: 종목코드, 종목명, 시장, 상장/상폐 상태
  - `dim_etf`: ETF 코드, 이름, 운용사, 레버리지/인버스/합성/해외형 분류
  - `fact_stock_daily`: 전 종목 일봉 OHLCV, 거래대금, 시가총액, 상장주식수 proxy
  - `fact_etf_daily`: ETF 일봉, NAV, 괴리율, 거래대금
  - `fact_etf_holdings`: ETF PDF 구성종목, 보유수량, 평가금액, 비중
  - `fact_market_index_daily`: KOSPI/KOSDAQ/KOSPI200 등 시장지수
  - `fact_kfi_scores`: 종목별 K-FI 점수와 구성요소
  - `fact_event_validation`: 이벤트별 수익률, 초과 하락률, 회귀 입력값
  - `etl_run_log`, `data_quality_check`: 실행 이력과 품질검사 결과
- 주요 제약:
  - fact table unique key는 `(date, ticker)` 또는 `(as_of_date, etf_ticker, stock_ticker)`.
  - 조회 최적화를 위해 `(ticker, date)`, `(date)`, `(kfi_korea desc)` 인덱스를 생성한다.

## K-FI Development
- `K-FI Base`:
  - `ETF Ownership Pressure = ETF 보유 주식수 / 상장주식수 또는 유동주식수`
  - `Liquidity Shock Pressure = ETF 보유 평가액 / 최근 20거래일 평균 거래대금`
- `K-FI Korea`:
  - Base 구성요소에 한국 ETF 시장 특성을 추가한다.
  - `Leveraged/Inverse Pressure`: 레버리지·인버스 ETF 노출
  - `Deviation Stress`: ETF 괴리율 가중 노출
  - `Flow/Trading Stress`: ETF 거래대금 급증 또는 순유출입 proxy
- MVP 기본 산식:
  - `K-FI Korea = 0.30*z(ownership) + 0.30*z(liquidity) + 0.15*z(leveraged_inverse) + 0.15*z(deviation) + 0.10*z(flow_proxy)`
- 결측 정책:
  - 유동주식수 미확보 시 `시가총액 / 종가`로 상장주식수 proxy 사용.
  - 수동 CSV가 있으면 수동 유동주식수를 우선 적용.
  - 모든 proxy 사용 여부는 `data_quality_flags`에 기록한다.

## Validation
- 기본 이벤트:
  - 보고서 기준 `2026-03-03`, `2026-03-04`
  - 추가 이벤트는 `configs/events.yml`에 등록
- 검증 방식:
  - `excess_drop = -(stock_return - market_return)`로 초과 하락률 정의
  - 회귀식: `excess_drop ~ K-FI + log(market_cap) + volatility_20d + turnover + beta + event fixed effects`
  - HC3 robust standard error 사용
  - K-FI 상위 decile과 하위 decile의 평균 초과 하락률 비교
  - 급락일이 아닌 placebo date에서 설명력이 약해지는지 확인
  - `K-FI Base`와 `K-FI Korea`의 설명력, 계수 방향, 유의성 비교
- 성공 기준:
  - `K-FI Korea` 계수가 양수이고 통계적으로 유의하거나, 최소한 Base 대비 설명력과 decile 분리가 개선된다.
  - 결과가 대시보드와 CSV/HTML 리포트로 재현 가능하다.

## Test Plan
- ETL 테스트:
  - 중복 적재 시 idempotent upsert 확인
  - 휴장일/빈 응답/일부 종목 결측 처리 확인
  - ETF PDF 구성종목 티커 매칭률 검사
- DB 테스트:
  - unique key, FK, partition 생성, 인덱스 존재 여부 확인
  - 핵심 쿼리의 결과 row 수와 결측률 검사
- K-FI 테스트:
  - 0 거래대금, ETF 미보유 종목, 결측 괴리율, 레버리지 분류 처리 확인
  - synthetic fixture에서 구성요소와 최종 점수 계산값 검증
- 검증 테스트:
  - synthetic event data에서 K-FI가 높은 종목의 초과 하락률이 더 크게 나오는지 확인
  - 이벤트별 회귀 결과 파일과 대시보드 입력 테이블 생성 확인
