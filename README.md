# BITAmin Korean ETF Fragility Index

한국 주식 전 종목 일봉 데이터베이스를 구축하고, ETF 보유 구조 기반의 한국형 Fragility Index(`K-FI`)를 개발 및 검증하는 MVP 프로젝트입니다.

## Stack

- PostgreSQL: 전 종목/ETF/지표/검증 데이터 저장
- Python ETL: `pykrx` 기반 KRX 공개 데이터 수집과 정규화
- Airflow: 일 단위 ETL 및 K-FI/검증 DAG
- Docker Compose: 로컬 재현 환경
- Streamlit: K-FI 랭킹과 이벤트 검증 대시보드

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

일부 KRX/pykrx 환경에서는 `.env`에 `KRX_ID`, `KRX_PW`가 필요할 수 있습니다.

서비스:

- Airflow: http://localhost:8080 (`admin` / `admin`)
- Streamlit: http://localhost:8501
- PostgreSQL: `localhost:5432`
- PgAdmin optional: `docker compose --profile tools up pgadmin`

## Local Python

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Python 3.14 환경에서는 일부 데이터/통계 패키지 wheel이 없을 수 있어 Python 3.11 또는 3.12를 권장합니다.

## CLI

```bash
bitamin-finance init-db
bitamin-finance ingest --date 2026-03-03 --target all
bitamin-finance build-kfi --date 2026-03-03 --max-etfs 50
```

`--max-etfs`는 빠른 MVP 테스트용입니다. 전체 수집 시 생략합니다.

“종목별 ETF 편입 현황” CSV export:

```bash
bitamin-finance export-exposure --date 2025-06-30 --output-dir data/processed/exposure_20250630
```

이 명령은 종목 기준 파일뿐 아니라 `*_etf_constituents.csv`,
`*_etf_constituent_summary.csv`도 함께 만들어 ETF 구성 종목 정보, 보유 주식 수,
ETF 내 비중을 확인할 수 있게 합니다.

2025년 상반기 전 종목 가격 DB 백필:

```bash
bitamin-finance backfill --start-date 2025-01-02 --end-date 2025-06-30 --target stock
```

자세한 사용법은 [docs/0510_meeting_usage.md](docs/0510_meeting_usage.md)를 참고합니다.
DB 테이블과 CSV 산출물 컬럼 정의는 [docs/data_specification.md](docs/data_specification.md)에 정리되어 있습니다.
처음 사용하는 분은 [docs/beginner_onboarding.md](docs/beginner_onboarding.md)를 먼저 읽으면 됩니다.
전체 워크플로우는 [docs/workflow.html](docs/workflow.html)에서 시각적으로 확인할 수 있습니다.

## Collaboration Notes

팀원 또는 새 Codex 세션이 이어서 작업할 때는 먼저 [AGENTS.md](AGENTS.md)를 확인합니다.
`AGENTS.md`에는 프로젝트 의도, 주요 파일 위치, 변경 시 함께 수정해야 하는 문서, 검증 명령이 정리되어 있습니다.

작업물이 바뀌면 다음 문서도 같이 맞춥니다.

- 실행 방법이나 주요 명령이 바뀌면 `README.md`
- DB 테이블, CSV 컬럼, K-FI 산식이 바뀌면 `docs/data_specification.md`
- 0510 회의 요구사항 수행 절차가 바뀌면 `docs/0510_meeting_usage.md`
- Codex/팀원 작업 규칙이나 주의사항이 바뀌면 `AGENTS.md`

## Airflow DAGs

- `dag_stock_daily_ingest`: 전 종목 일봉과 시장지수 적재
- `dag_etf_daily_ingest`: ETF 일봉, 괴리율, PDF 구성종목 적재
- `dag_kfi_build`: DB에 적재된 데이터를 기반으로 K-FI 산출
- `dag_kfi_validation`: 이벤트일 기준 초과 하락률과 회귀 입력 테이블 생성

`dag_kfi_validation`은 trigger conf로 다음 값을 받을 수 있습니다.

```json
{
  "event_date": "2026-03-03",
  "score_date": "2026-03-03",
  "market_index": "KOSPI"
}
```

## K-FI Definition

`K-FI Base`

- `ETF Ownership Pressure = ETF 보유 주식수 / 상장주식수 또는 유동주식수`
- `Liquidity Shock Pressure = ETF 보유 평가액 / 최근 20거래일 평균 거래대금`

`K-FI Korea`

```text
0.30*z(ownership)
+ 0.30*z(liquidity)
+ 0.15*z(leveraged_inverse)
+ 0.15*z(deviation)
+ 0.10*z(flow_proxy)
```

검증은 이벤트일의 `excess_drop = -(stock_return - market_return)`을 종속변수로 두고, K-FI와 통제변수의 관계를 회귀 및 decile test로 확인합니다.

## Manual Data

공개 데이터로 자동 수집이 어려운 유동주식수 등은 `data/manual/`에 같은 ticker/date 스키마의 CSV를 추가한 뒤 ETL 로더를 확장하는 방식으로 반영합니다. 현재 MVP는 `market_cap / close` 기반 상장주식수 proxy를 사용하고 `data_quality_flags`에 기록합니다.
