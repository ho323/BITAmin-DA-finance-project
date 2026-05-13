# K-FI 프로젝트 사용자 가이드

이 가이드는 BITAmin Korean ETF Fragility Index 프로젝트를 처음 사용하는 분을 위한 안내서입니다. 금융공학을 깊게 알지 않아도 괜찮습니다. 기본적인 AI/CS 지식이 있다면, 이 문서만으로 프로젝트의 목적과 실행 흐름을 따라갈 수 있습니다.

이 가이드를 읽고 나면 다음을 할 수 있어야 합니다.

1. 이 프로젝트가 무엇을 분석하는지 설명할 수 있습니다.
2. KRX 데이터가 어떤 테이블과 CSV 파일로 바뀌는지 이해할 수 있습니다.
3. 로컬에서 주요 명령을 실행해 ETF 편입 노출 데이터를 만들 수 있습니다.
4. `K-FI Korea` 점수와 이벤트 검증 결과를 해석할 수 있습니다.

## 1. 이 프로젝트는 무엇인가요?

이 프로젝트는 ETF가 어떤 주식을 얼마나 많이 보유하고 있는지 분석해서, 시장 충격이 왔을 때 더 취약할 수 있는 한국 주식 종목을 점수화합니다.

이 점수를 `K-FI Korea`라고 부릅니다.

핵심 아이디어는 단순합니다.

- ETF는 여러 주식을 묶어 사고파는 상품입니다.
- 어떤 주식이 여러 ETF에 많이 들어 있으면, ETF 매매 충격이 그 주식에도 전달될 수 있습니다.
- 특히 평소 거래대금이 작거나, 레버리지/인버스 ETF 노출이 크거나, ETF 괴리율이 커지면 충격이 더 커질 수 있습니다.
- 이 프로젝트는 이런 취약성을 점수로 만들고, 실제 이벤트일에 점수가 높은 종목이 더 크게 하락했는지 검증합니다.

## 2. 쉽게 이해하는 비유

주식시장을 물류 창고라고 생각해 보겠습니다.

- 개별 주식은 창고 안의 물건입니다.
- ETF는 여러 물건을 한 번에 담은 박스입니다.
- 투자자들이 ETF 박스를 대량으로 사고팔면, 박스 안에 들어 있는 물건들도 같이 움직일 수 있습니다.
- 어떤 물건이 여러 박스에 많이 들어 있고, 평소 거래량은 많지 않다면, 박스 주문이 몰릴 때 그 물건은 더 크게 흔들릴 수 있습니다.

`K-FI`는 "이 주식이 ETF 매매 충격에 얼마나 흔들릴 수 있는가"를 숫자로 나타낸 지표입니다.

## 3. 이 프로젝트가 답하려는 질문

이 프로젝트의 중심 질문은 다음과 같습니다.

> ETF 보유 구조를 보면, 이벤트일에 더 크게 빠질 수 있는 종목을 미리 찾을 수 있을까요?

이를 위해 아래 질문을 순서대로 해결합니다.

1. 한국 주식 전 종목의 가격, 거래대금, 시가총액을 모읍니다.
2. ETF가 보유한 구성종목, 보유수량, 평가금액, 비중을 모읍니다.
3. 종목별로 ETF가 들고 있는 총 주식 수와 평가금액을 계산합니다.
4. 그 노출을 바탕으로 K-FI 취약성 점수를 만듭니다.
5. 이벤트일 수익률로 그 점수가 실제 설명력을 갖는지 검증합니다.

## 4. 먼저 알아둘 용어

| 용어 | 쉬운 설명 | 프로젝트에서 쓰이는 곳 |
| --- | --- | --- |
| ETF | 여러 주식이나 자산을 묶어 거래하는 펀드 상품 | ETF universe, ETF daily, ETF holdings |
| PDF | ETF가 실제로 들고 있는 구성종목 목록. Portfolio Deposit File | `fact_etf_holdings` |
| NAV | ETF의 이론적인 순자산가치 | `fact_etf_daily.nav` |
| 괴리율 | ETF 시장가격이 NAV에서 얼마나 벗어났는지 나타내는 값 | `deviation_stress` |
| 거래대금 | 가격과 거래량을 함께 반영한 유동성 지표 | `liquidity_pressure`, `flow_stress` |
| 상장주식수 proxy | 실제 유동주식수가 없을 때 사용하는 대체 주식수 | `listed_shares_proxy` |
| K-FI | ETF 구조 기반 취약성 점수 | `fact_kfi_scores` |
| 초과 하락률 | 시장 대비 개별 종목이 더 빠진 정도 | `fact_event_validation.excess_drop` |
| decile test | 점수를 10개 그룹으로 나눠 높은 그룹과 낮은 그룹을 비교하는 검증 | validation |

## 5. 전체 흐름

가장 중요한 흐름은 아래와 같습니다.

```text
KRX/pykrx 데이터
→ Python 수집/정규화
→ PostgreSQL 적재
→ ETF 노출 계산
→ K-FI 점수 계산
→ 이벤트 검증
→ Streamlit/CSV 리포트
```

각 단계의 역할은 다음과 같습니다.

| 단계 | 하는 일 | 주요 파일 |
| --- | --- | --- |
| 수집 | KRX/pykrx에서 주식, ETF, 지수 데이터를 가져옵니다 | `src/bitamin_finance/data/krx_client.py` |
| 적재 | pandas DataFrame을 PostgreSQL 테이블에 저장합니다 | `src/bitamin_finance/etl/jobs.py`, `src/bitamin_finance/etl/loaders.py` |
| DB | 원천 데이터와 계산 결과를 날짜별로 저장합니다 | `sql/001_schema.sql` |
| 노출 계산 | 종목별 ETF 보유 주식 수와 평가금액을 계산합니다 | `src/bitamin_finance/features/exposure.py` |
| K-FI 계산 | ETF 보유 압력과 유동성 압력을 점수화합니다 | `src/bitamin_finance/features/kfi.py` |
| 검증 | 이벤트일 초과 하락률과 K-FI의 관계를 확인합니다 | `src/bitamin_finance/validation/event_study.py` |
| 화면 | 결과를 대시보드로 보여줍니다 | `app/streamlit_app.py` |

전체 구조를 그림으로 보고 싶다면 `docs/workflow.html`을 브라우저에서 열어 보세요.

## 6. 데이터는 어디에 저장되나요?

수집한 데이터는 PostgreSQL의 `bitamin` schema에 저장됩니다.

### 6.1 원천 데이터 테이블

- `dim_stock`: 종목 목록
- `dim_etf`: ETF 목록과 레버리지/인버스 등 분류
- `fact_stock_daily`: 전 종목 주식 일봉
- `fact_etf_daily`: ETF 일봉, NAV, 괴리율
- `fact_etf_holdings`: ETF가 보유한 종목과 수량
- `fact_market_index_daily`: KOSPI, KOSDAQ, KOSPI200 지수

### 6.2 계산 결과 테이블

- `fact_kfi_scores`: K-FI 점수
- `fact_event_validation`: 이벤트 검증 결과
- `etl_run_log`: ETL 실행 이력
- `data_quality_check`: 데이터 품질검사 결과

같은 날짜를 다시 실행해도 primary key 기준으로 업데이트됩니다. 수집이 중간에 멈췄다면 같은 명령을 다시 실행하세요.

## 7. 어떤 CSV 파일이 만들어지나요?

회의나 분석에서 바로 보기 좋은 파일은 `export-exposure` 명령으로 만듭니다.

- `*_stock_etf_exposure_summary.csv`: 종목별 ETF 보유 총량 요약
- `*_stock_etf_exposure_detail.csv`: 종목-ETF 단위 상세
- `*_stock_etf_exposure_matrix.csv`: 종목 x ETF wide matrix
- `*_etf_constituents.csv`: ETF별 구성종목 상세
- `*_candidate_stocks.csv`: ETF 노출 기준 후보 종목

처음에는 `*_stock_etf_exposure_summary.csv`를 먼저 보세요. 여기서 `etf_ownership_ratio`가 큰 종목은 ETF가 상대적으로 많이 들고 있는 종목입니다.

## 8. K-FI는 어떻게 계산하나요?

K-FI는 두 가지 기본 생각에서 출발합니다.

1. ETF가 그 종목을 많이 들고 있으면 취약할 수 있습니다.
2. 그 종목의 평소 거래대금이 작으면 ETF 충격을 흡수하기 어렵습니다.

### 8.1 K-FI Base

```text
0.50 * z(ownership_pressure)
+ 0.50 * z(liquidity_pressure)
```

- `ownership_pressure`: ETF 보유 주식수 / 상장주식수 proxy
- `liquidity_pressure`: ETF 보유 평가금액 / 최근 20거래일 평균 거래대금

### 8.2 K-FI Korea

```text
0.30 * z(ownership_pressure)
+ 0.30 * z(liquidity_pressure)
+ 0.15 * z(leveraged_inverse_pressure)
+ 0.15 * z(deviation_stress)
+ 0.10 * z(flow_stress)
```

추가 항목은 한국 ETF 시장 특성을 반영합니다.

- `leveraged_inverse_pressure`: 레버리지/인버스 ETF에 얼마나 노출되어 있는지 나타냅니다.
- `deviation_stress`: 괴리율이 큰 ETF에 얼마나 노출되어 있는지 나타냅니다.
- `flow_stress`: ETF 거래대금이 평소보다 얼마나 튀었는지 나타냅니다.

여기서 `z(...)`는 서로 단위가 다른 값을 비교 가능하게 표준화하는 과정입니다.

## 9. 검증은 무엇을 보나요?

검증은 "K-FI가 높은 종목이 이벤트일에 실제로 더 크게 빠졌는가?"를 확인합니다.

핵심 값은 `excess_drop`입니다.

```text
excess_drop = -(stock_return - market_return)
```

예를 들어 시장이 -2% 빠졌는데 어떤 종목이 -8% 빠졌다면, 그 종목은 시장보다 6%p 더 나쁘게 움직였습니다. 이 값을 초과 하락률로 봅니다.

검증 방식은 두 가지입니다.

- decile test: K-FI 점수 순서로 10개 그룹을 만들고, 높은 그룹이 더 크게 하락했는지 봅니다.
- regression: 시가총액, 변동성, 회전율 같은 통제변수를 넣고도 K-FI가 설명력을 갖는지 봅니다.

## 10. 처음 실행하는 순서

아래 순서대로 실행하면 로컬에서 기본 흐름을 경험할 수 있습니다.

### 10.1 Python 환경 준비

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Python 3.11 또는 3.12 사용을 권장합니다.

### 10.2 테스트 실행

```bash
.venv/bin/pytest -q
```

테스트가 통과하면 계산 함수와 기본 구조가 정상적으로 동작한다는 뜻입니다.

### 10.3 PostgreSQL 시작

```bash
docker compose up -d postgres
```

### 10.4 DB schema 적용

```bash
.venv/bin/bitamin-finance init-db
```

### 10.5 2025년 상반기 주식 가격 적재

```bash
.venv/bin/bitamin-finance backfill \
  --start-date 2025-01-02 \
  --end-date 2025-06-30 \
  --target stock
```

시장지수도 함께 적재합니다.

```bash
.venv/bin/bitamin-finance backfill \
  --start-date 2025-01-02 \
  --end-date 2025-06-30 \
  --target market-index
```

주의할 날짜가 있습니다.

- `2025-01-01`은 휴장일입니다.
- `2025-06-31`은 존재하지 않는 날짜입니다.
- 이 프로젝트의 주요 분석 기간은 `2025-01-02`부터 `2025-06-30`까지입니다.

### 10.6 ETF 기준일 데이터 수집

처음에는 일부 ETF만 수집해서 동작을 확인하세요.

```bash
.venv/bin/bitamin-finance ingest \
  --date 2025-06-30 \
  --target etf \
  --max-etfs 20
```

전체 수집은 `--max-etfs`를 빼고 실행합니다.

```bash
.venv/bin/bitamin-finance ingest \
  --date 2025-06-30 \
  --target etf
```

ETF PDF 구성종목 수집은 KRX 로그인 정보가 필요할 수 있습니다. `.env`에 아래 값을 설정하세요.

```env
KRX_ID=...
KRX_PW=...
```

### 10.7 ETF 편입 노출 CSV 만들기

```bash
.venv/bin/bitamin-finance export-exposure \
  --date 2025-06-30 \
  --from-db \
  --output-dir data/processed/exposure_20250630
```

먼저 아래 파일을 확인하세요.

```text
data/processed/exposure_20250630/20250630_stock_etf_exposure_summary.csv
```

`etf_ownership_ratio`가 큰 종목은 ETF가 상대적으로 많이 보유한 종목입니다.

### 10.8 시계열 CSV 만들기

DB에 쌓인 주식, ETF, 시장지수, K-FI, 검증 데이터를 기간 조건으로 CSV로 뽑을 수 있습니다.

```bash
.venv/bin/bitamin-finance export-timeseries \
  --target stock \
  --start-date 2025-01-02 \
  --end-date 2025-06-30 \
  --output data/processed/timeseries/stock_2025_h1.csv
```

특정 종목만 뽑고 싶으면 `--ticker`를 사용합니다.

```bash
.venv/bin/bitamin-finance export-timeseries \
  --target stock \
  --start-date 2025-01-02 \
  --end-date 2025-06-30 \
  --ticker 005930,000660 \
  --output data/processed/timeseries/semiconductor_2025_h1.csv
```

ETF는 `--target etf --etf-ticker ...`, 시장지수는 `--target market-index --index-name KOSPI`처럼 사용합니다.

### 10.9 대시보드 실행

전체 서비스를 실행하면 Streamlit과 Airflow도 함께 사용할 수 있습니다.

```bash
docker compose up --build
```

접속 주소는 다음과 같습니다.

- Streamlit: http://localhost:8501
- Airflow: http://localhost:8080
- PostgreSQL: localhost:5432

## 11. 결과를 확인하는 순서

아래 항목을 순서대로 확인하면 결과가 제대로 만들어졌는지 판단하기 쉽습니다.

1. `fact_stock_daily`에 2025-01-02부터 2025-06-30까지 데이터가 쌓였는지 확인합니다.
2. `fact_etf_holdings`에 기준일 ETF 구성종목 데이터가 쌓였는지 확인합니다.
3. `*_stock_etf_exposure_summary.csv`에 `etf_ownership_ratio`가 계산되었는지 확인합니다.
4. ETF 노출이 큰 후보 종목이 상식적으로 이해 가능한지 확인합니다.
5. K-FI 결과에서 `kfi_korea`가 비어 있지 않은지 확인합니다.
6. 이벤트 검증에서 decile별 `avg_excess_drop`이 비교 가능한 형태로 나왔는지 확인합니다.

## 12. 추천 학습 순서

처음 사용하는 경우 아래 순서로 보면 가장 덜 헷갈립니다.

1. `docs/workflow.html`을 열어 전체 그림을 봅니다.
2. 이 가이드에서 용어와 실행 흐름을 확인합니다.
3. `README.md`에서 설치와 주요 명령을 확인합니다.
4. `docs/0510_meeting_usage.md`에서 회의 요구사항 기준 실행법을 확인합니다.
5. `docs/data_specification.md`에서 DB와 CSV 컬럼 정의를 확인합니다.
6. `src/bitamin_finance/features/exposure.py`에서 ETF 노출 계산 코드를 봅니다.
7. `src/bitamin_finance/features/kfi.py`에서 K-FI 산식 구현을 봅니다.
8. `src/bitamin_finance/validation/event_study.py`에서 이벤트 검증 코드를 봅니다.

## 13. 권장 실습 코스

처음부터 전체 수집을 돌리기보다 작은 범위로 확인하는 것이 좋습니다.

1. 테스트를 실행합니다.

```bash
.venv/bin/pytest -q
```

2. PostgreSQL만 먼저 실행합니다.

```bash
docker compose up -d postgres
```

3. DB schema를 적용합니다.

```bash
.venv/bin/bitamin-finance init-db
```

4. ETF 일부만 smoke test로 수집합니다.

```bash
.venv/bin/bitamin-finance ingest \
  --date 2025-06-30 \
  --target etf \
  --max-etfs 20
```

5. exposure CSV를 생성하고 summary 파일을 확인합니다.

```bash
.venv/bin/bitamin-finance export-exposure \
  --date 2025-06-30 \
  --from-db \
  --output-dir data/processed/exposure_test
```

6. `etf_ownership_ratio` 상위 종목을 확인합니다.

7. `src/bitamin_finance/features/kfi.py`를 열어 산식이 코드로 어떻게 구현되어 있는지 확인합니다.

## 14. 자주 묻는 질문

### DB 없이도 사용할 수 있나요?

일부 CSV export는 live pykrx 수집으로 가능합니다. 다만 재현성과 검증을 위해서는 DB 적재 흐름을 사용하는 것을 권장합니다.

### 왜 ETF holdings가 중요한가요?

ETF 가격만 보면 ETF 자체의 움직임만 알 수 있습니다. ETF holdings를 봐야 어떤 개별 종목이 ETF 충격에 노출되어 있는지 알 수 있습니다.

### 왜 `--max-etfs`를 쓰나요?

ETF 전체 PDF 수집은 오래 걸릴 수 있습니다. 처음에는 `--max-etfs 20` 같은 옵션으로 코드, 계정, 네트워크가 동작하는지 먼저 확인하세요.

### 왜 z-score를 쓰나요?

보유 비율, 거래대금 비율, 괴리율은 단위와 크기가 다릅니다. z-score로 표준화해야 한 점수 안에서 비교 가능하게 합칠 수 있습니다.

### K-FI가 높으면 무조건 하락한다는 뜻인가요?

아닙니다. K-FI는 예언 모델이 아니라 구조적 취약성 지표입니다. 시장 이벤트가 있을 때 더 민감할 가능성을 보는 지표에 가깝습니다.

## 15. 미니 계산 예시

상장주식수가 1,000주인 A 종목이 있다고 가정해 보겠습니다.

- ETF 1이 A 종목 100주를 보유합니다.
- ETF 2가 A 종목 50주를 보유합니다.
- 총 ETF 보유 주식수는 150주입니다.

그러면 ownership pressure는 다음과 같습니다.

```text
150 / 1,000 = 0.15
```

즉 A 종목의 15%가 ETF holdings에 잡혀 있습니다.

이번에는 거래대금을 보겠습니다.

- A 종목의 최근 20일 평균 거래대금이 1억 원입니다.
- ETF들이 보유한 A 종목 평가금액이 5억 원입니다.

그러면 liquidity pressure는 다음과 같습니다.

```text
5억 / 1억 = 5.0
```

이 값이 크다는 것은 ETF 쪽 보유 규모가 평소 거래 유동성에 비해 크다는 뜻입니다.

## 16. 이 가이드를 마친 뒤 할 수 있어야 하는 일

아래 항목을 스스로 할 수 있다면 프로젝트의 기본 사용 흐름을 이해한 것입니다.

- 이 프로젝트가 왜 ETF holdings를 모으는지 설명할 수 있습니다.
- `docker compose`와 CLI로 DB를 초기화할 수 있습니다.
- 2025년 상반기 주식/지수 데이터를 백필할 수 있습니다.
- 기준일 ETF holdings를 smoke test로 수집할 수 있습니다.
- 종목별 ETF 편입 노출 CSV를 만들고 `etf_ownership_ratio`를 해석할 수 있습니다.
- K-FI 산식의 각 component가 무엇을 뜻하는지 설명할 수 있습니다.
- 이벤트 검증에서 `excess_drop`이 무엇인지 이해할 수 있습니다.
