"""Database engine + session factory."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(dsn: str) -> Engine:
    return create_engine(dsn, pool_pre_ping=True, future=True)


def make_session_factory(dsn: str) -> sessionmaker[Session]:
    return sessionmaker(bind=make_engine(dsn), expire_on_commit=False, future=True)
