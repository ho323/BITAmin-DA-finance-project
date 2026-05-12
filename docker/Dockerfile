FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AIRFLOW_HOME=/opt/airflow

ARG AIRFLOW_VERSION=2.10.5
ARG PYTHON_VERSION=3.11

WORKDIR /opt/project

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install \
    "apache-airflow==${AIRFLOW_VERSION}" \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

COPY pyproject.toml README.md /opt/project/
COPY src /opt/project/src
RUN pip install -e ".[dev]"

COPY app /opt/project/app
COPY configs /opt/project/configs
COPY sql /opt/project/sql
