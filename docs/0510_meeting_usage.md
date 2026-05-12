# 0510 회의 요구사항 사용법

## 1. 한 기준일의 ETF 편입 노출 데이터 뽑기

DB 없이 바로 `pykrx`에서 수집해서 CSV로 저장:

```bash
.venv/bin/bitamin-finance export-exposure \
  --date 2025-06-30 \
  --output-dir data/processed/exposure_20250630
```

만약 실행 중 `KRX_ID` 또는 `KRX_PW` 관련 오류가 나오면 `.env`에 KRX 접근 계정을 추가한 뒤 다시 실행합니다.

```bash
KRX_ID=...
KRX_PW=...
```

빠른 테스트:

```bash
.venv/bin/bitamin-finance export-exposure \
  --date 2025-06-30 \
  --max-etfs 20 \
  --output-dir data/processed/exposure_test
```

DB에 이미 적재한 데이터를 기준으로 export:

```bash
.venv/bin/bitamin-finance export-exposure \
  --date 2025-06-30 \
  --from-db \
  --output-dir data/processed/exposure_20250630
```

## 2. 생성 파일

- `*_stock_etf_exposure_summary.csv`
  - 종목별 ETF 보유 주식수 합계
  - 상장주식수 proxy
  - `etf_ownership_ratio`
  - ETF 편입 개수
- `*_stock_etf_exposure_detail.csv`
  - 종목-ETF 단위 상세 테이블
  - 어떤 ETF가 해당 종목을 몇 주 보유하는지
  - 해당 ETF 안에서의 비중
  - 해당 종목 전체 주식수 대비 보유 비율
- `*_stock_etf_exposure_matrix.csv`
  - 행은 종목, 열은 ETF
  - 값은 `ETF 보유 주식수 / 종목 상장주식수 proxy`
- `*_etf_constituent_summary.csv`
  - ETF별 구성 종목 수
  - ETF별 총 보유 주식 수 합계
  - ETF별 총 평가금액
  - ETF 내 최대 비중 종목
- `*_etf_constituents.csv`
  - ETF별 구성 종목 상세
  - 보유 종목 코드/이름
  - 보유 주식 수
  - 평가금액
  - ETF 내 비중
  - 종목 전체 상장주식수 proxy 대비 ETF 보유 비율
- `*_candidate_stocks.csv`
  - ETF 편입 비중 기준 후보 종목 리스트

## 3. 후보 종목 필터링

회의에서 말한 “ETF 보유 비중이 일정 이상인 종목만 먼저 보자”는 아래처럼 실행합니다.

```bash
.venv/bin/bitamin-finance export-exposure \
  --date 2025-06-30 \
  --min-ownership-ratio 0.05 \
  --min-etf-count 2 \
  --top-n 100 \
  --output-dir data/processed/exposure_candidates
```

`0.05`는 5%입니다. 회의에서 말한 것처럼 먼저 데이터를 뽑아보고 5%, 10% 같은 기준을 조정하면 됩니다.

## 4. 2025년 상반기 가격 DB 백필

회의록의 “2025년 1월부터 6월까지”는 달력상 `2025-06-31`이 없어서 `2025-06-30`으로 잡습니다.

```bash
docker compose up -d postgres
.venv/bin/bitamin-finance init-db
.venv/bin/bitamin-finance backfill \
  --start-date 2025-01-02 \
  --end-date 2025-06-30 \
  --target stock
```

시장지수까지 같이:

```bash
.venv/bin/bitamin-finance backfill \
  --start-date 2025-01-02 \
  --end-date 2025-06-30 \
  --target market-index
```

ETF holdings는 날짜별 전체 수집이 오래 걸릴 수 있으므로, 우선 기준일 하나를 정해서 구성 종목이 일정하다고 가정하고 시작합니다.

```bash
.venv/bin/bitamin-finance ingest --date 2025-06-30 --target etf
```

## 5. 회의에서 합의한 분석 가정

- 초기 MVP는 전 종목 일반화보다 “ETF 편입 비중이 높은 후보 종목”으로 범위를 좁힌다.
- ETF 구성종목은 짧은 검증 기간 동안 크게 변하지 않는다고 가정한다.
- 후보 종목 선정 후, ETF 가격/거래 충격과 개별 종목 초과 하락률의 관계를 K-FI로 검증한다.
