# AGENTS.md

이 문서는 Codex, 팀원, 새 채팅 세션이 프로젝트의 의도와 구조를 빠르게 이해하고 같은 기준으로 작업하기 위한 운영 가이드다. 코드 변경 전후로 이 파일과 README, docs를 함께 확인한다.

## Project Intent

이 프로젝트의 핵심 목표는 한국 주식시장에 맞춘 ETF 기반 Fragility Index를 개발하고 검증하는 것이다.

- 전 종목 주식 일봉 데이터를 PostgreSQL에 축적한다.
- ETF 일봉, NAV/괴리율, ETF PDF 구성종목, 보유수량, 평가금액, 비중을 수집한다.
- 종목별 ETF 보유 압력과 유동성 충격 압력을 계산한다.
- 한국 ETF 시장 특성을 반영한 `K-FI Korea`를 산출한다.
- 이벤트일 초과 하락률, decile test, 회귀분석으로 설명력을 검증한다.
- Streamlit과 CSV/HTML 리포트로 팀원이 재현 가능한 결과를 확인하게 한다.

현재 회의 기준 주요 분석 기간은 `2025-01-02`부터 `2025-06-30`까지다. `2025-01-01`은 휴장일이고 `2025-06-31`은 존재하지 않는다.

## Stack

- Python package: `src/bitamin_finance`
- DB: PostgreSQL, schema `bitamin`
- ETL: Python CLI plus Airflow DAGs
- Data source: `pykrx==1.2.8`
- Dashboard: Streamlit
- Local orchestration: Docker Compose
- Python target: `>=3.11`

Important dependency constraints:

- `SQLAlchemy>=1.4,<2.0` is intentional because Airflow 2.x can break with SQLAlchemy 2.x.
- `pykrx==1.2.8` is intentional because ETF PDF/KRX login behavior was verified against this version.
- Python 3.11 or 3.12 is recommended for team setup. Python 3.14 may work locally but can have package wheel issues.

## Repository Map

| Path | Purpose |
| --- | --- |
| `README.md` | Human-facing setup, commands, project overview |
| `AGENTS.md` | Codex/team operating guide and maintenance rules |
| `PLAN.md` | Initial implementation plan and project roadmap |
| `sql/001_schema.sql` | PostgreSQL schema, partitions, indexes |
| `docker-compose.yml` | Local Postgres, Airflow, Streamlit services |
| `docker/Dockerfile` | Airflow/Streamlit image build |
| `dags/kfi_pipeline_dags.py` | Airflow DAG definitions |
| `app/streamlit_app.py` | Streamlit dashboard |
| `src/bitamin_finance/cli.py` | CLI entrypoint: `bitamin-finance` |
| `src/bitamin_finance/config.py` | `.env` and settings loading |
| `src/bitamin_finance/data/krx_client.py` | KRX/pykrx live data collection |
| `src/bitamin_finance/data/classifiers.py` | ETF name-based classifier |
| `src/bitamin_finance/db/connection.py` | SQLAlchemy connection helpers |
| `src/bitamin_finance/db/schema.py` | Schema application and partition helpers |
| `src/bitamin_finance/etl/jobs.py` | Ingest/build/validation jobs |
| `src/bitamin_finance/etl/loaders.py` | DataFrame upsert and ETL logs |
| `src/bitamin_finance/features/exposure.py` | ETF exposure CSV table builders |
| `src/bitamin_finance/features/kfi.py` | K-FI component and score calculation |
| `src/bitamin_finance/validation/event_study.py` | Event return, controls, regression helpers |
| `src/bitamin_finance/reporting/exports.py` | Report export utilities |
| `configs/events.yml` | Event date configuration |
| `docs/0510_meeting.md` | Meeting notes |
| `docs/0510_meeting_usage.md` | Meeting-specific usage guide |
| `docs/data_specification.md` | DB/CSV/K-FI data specification |
| `docs/workflow.html` | Visual project workflow page for teammates |
| `tests/` | Unit tests for classifiers, exposure, K-FI, validation, CLI import |

## Data Model Summary

Primary DB tables live under the `bitamin` schema.

- `dim_stock`: stock master
- `dim_etf`: ETF master and ETF type flags
- `fact_stock_daily`: stock OHLCV, trading value, market cap, listed shares proxy
- `fact_etf_daily`: ETF OHLCV, NAV, deviation rate
- `fact_etf_holdings`: ETF PDF constituents, shares, valuation amount, weight
- `fact_market_index_daily`: KOSPI/KOSDAQ/KOSPI200 daily index data
- `fact_kfi_scores`: K-FI component and final scores
- `fact_event_validation`: event validation frame
- `etl_run_log`: ETL run history
- `data_quality_check`: data quality results

Fact tables are yearly range partitioned by date. Upserts are idempotent by primary key, so rerunning the same date is expected and safe.

See `docs/data_specification.md` for full column definitions. If DB schema, CSV columns, or K-FI formulas change, update that file in the same change.

## K-FI Definition

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

Component meanings:

- `ownership_pressure`: ETF held shares divided by listed shares proxy.
- `liquidity_pressure`: ETF holding valuation amount divided by 20-trading-day average stock trading value.
- `leveraged_inverse_pressure`: leveraged/inverse ETF exposure share.
- `deviation_stress`: absolute ETF deviation rate weighted exposure.
- `flow_stress`: ETF trading value spike proxy weighted exposure.

## Common Commands

Local setup:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Start services:

```bash
docker compose up --build
```

Initialize DB:

```bash
.venv/bin/bitamin-finance init-db
```

Collect 2025 H1 stock and index data:

```bash
.venv/bin/bitamin-finance backfill --start-date 2025-01-02 --end-date 2025-06-30 --target stock
.venv/bin/bitamin-finance backfill --start-date 2025-01-02 --end-date 2025-06-30 --target market-index
```

Collect ETF snapshot:

```bash
.venv/bin/bitamin-finance ingest --date 2025-06-30 --target etf
```

Fast ETF smoke test:

```bash
.venv/bin/bitamin-finance ingest --date 2025-06-30 --target etf --max-etfs 20
```

Export exposure CSV from DB:

```bash
.venv/bin/bitamin-finance export-exposure --date 2025-06-30 --from-db --output-dir data/processed/exposure_20250630
```

Run tests:

```bash
.venv/bin/pytest -q
```

Check Docker Compose syntax:

```bash
docker compose config --quiet
```

## Environment

Use `.env.example` as the template. Local CLI should usually connect to `localhost`, while Docker services connect to the `postgres` hostname through `docker-compose.yml`.

KRX login is required for ETF PDF constituent collection:

```env
KRX_ID=...
KRX_PW=...
```

Do not commit real credentials or local generated data dumps unless explicitly requested.

## Working Rules for Codex and Team Members

Before changing code:

- Read this `AGENTS.md`, `README.md`, and any docs relevant to the requested area.
- Check the existing module patterns before adding new abstractions.
- Prefer small, focused changes that preserve the current CLI and DB contracts.
- Do not change dependency pins casually, especially Airflow, SQLAlchemy, and pykrx.

When changing data collection:

- Update `src/bitamin_finance/data/krx_client.py`.
- Keep KRX/pykrx response normalization robust to missing or overlapping columns.
- Preserve clean `KRXDataError` messages for user-actionable failures.
- If a collection target can run long, include progress output or a bounded smoke-test option.

When changing DB schema:

- Update `sql/001_schema.sql`.
- Update loader column lists in `src/bitamin_finance/etl/jobs.py`.
- Update `docs/data_specification.md`.
- Add or update tests where practical.
- Mention migration/reset implications in README or a docs file. This project currently applies a schema file for MVP development rather than a full Alembic migration system.

When changing CSV outputs:

- Update `src/bitamin_finance/features/exposure.py` or reporting modules.
- Update `docs/data_specification.md` section 5.
- Update `docs/0510_meeting_usage.md` if the meeting workflow changes.
- Keep filenames stable unless there is a strong reason to rename them.

When changing K-FI formulas:

- Update `src/bitamin_finance/features/kfi.py`.
- Update `README.md` K-FI section.
- Update `docs/data_specification.md` section 6.
- Add or update synthetic tests in `tests/test_kfi.py`.

When changing validation:

- Update `src/bitamin_finance/validation/event_study.py`.
- Update `configs/events.yml` when event defaults change.
- Update `docs/data_specification.md` section 7.
- Add or update tests in `tests/test_validation.py`.

When changing CLI behavior:

- Update `src/bitamin_finance/cli.py`.
- Update README command examples.
- Update `docs/0510_meeting_usage.md` if the command affects the meeting deliverables.
- Keep `.venv/bin/bitamin-finance ...` examples for local reproducibility.

When changing Docker/Airflow:

- Update `docker-compose.yml`, `docker/Dockerfile`, or `dags/kfi_pipeline_dags.py`.
- Run `docker compose config --quiet`.
- Keep Airflow dependency compatibility in mind.
- Update README service URLs or DAG descriptions if they change.

## Documentation Maintenance Checklist

For every meaningful code or data-contract change, ask:

- Does `README.md` still show the correct setup and main commands?
- Does `docs/data_specification.md` still match DB tables, CSV columns, and formulas?
- Does `docs/0510_meeting_usage.md` still match the 0510 meeting workflow?
- Does `AGENTS.md` need a new warning, command, or ownership note?
- Do tests cover the changed behavior?

Documentation expectations:

- README is for humans getting started and running the project.
- AGENTS is for future Codex/team contributors deciding how to work safely.
- `docs/data_specification.md` is the data dictionary and should match code.
- `docs/workflow.html` is the visual workflow overview and should stay aligned with the main pipeline.
- Meeting docs should stay practical and command-oriented.

## Verification Expectations

Minimum verification after most code changes:

```bash
.venv/bin/pytest -q
```

For Docker/Airflow changes:

```bash
docker compose config --quiet
```

For DB/ETL changes, use a bounded smoke test before a full run:

```bash
.venv/bin/bitamin-finance init-db
.venv/bin/bitamin-finance ingest --date 2026-03-03 --target all --max-etfs 5
```

If tests or live KRX checks cannot be run, state that clearly in the final response and explain why.

## Known Operational Notes

- ETF full holdings collection can be slow because ETF deviation and PDF endpoints are called per ETF.
- `--max-etfs` is for smoke tests only. Omit it for full collection.
- If collection stops midway, rerun the same command. Upsert keys make repeated dates safe.
- Current ETF holdings ingest writes after collecting the batch. If the process dies before the batch write, rerun the target.
- `fact_stock_daily.listed_shares_proxy` uses `listed_shares` first and falls back to `market_cap / close` when needed.
- Generated local data under `data/processed/`, `data/raw/`, `data/interim/`, and local DB volumes should not be treated as source code.
