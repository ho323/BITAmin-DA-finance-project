from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine

from bitamin_finance.config import load_settings


def get_engine(database_url: str | None = None) -> Engine:
    settings = load_settings()
    return create_engine(database_url or settings.database_url, pool_pre_ping=True)


@contextmanager
def begin_connection(database_url: str | None = None) -> Iterator[Connection]:
    engine = get_engine(database_url)
    with engine.begin() as connection:
        yield connection
