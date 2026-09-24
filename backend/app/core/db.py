"""Engine, session factory, declarative Base, the get_db dependency and `atomic`."""

import functools
from collections.abc import Callable, Iterator
from typing import Concatenate, ParamSpec, TypeVar

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# Stable constraint names, so errors and future migrations can refer to them.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def make_engine(url: str = settings.database_url):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        # Let SQLAlchemy issue BEGIN itself; pysqlite's own transaction handling breaks
        # SAVEPOINT, which `atomic` relies on.
        dbapi_conn.isolation_level = None
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")  # SQLite ignores FKs unless asked
        cur.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn):
        # Take the write lock up front: transactions run one at a time, so check-then-act
        # rules (balance due, quantity left to accept) can't race (D-47).
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """One session per request. The router commits after the service call returns; anything
    left uncommitted is rolled back when the session closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


P = ParamSpec("P")
R = TypeVar("R")


def atomic(fn: Callable[Concatenate[Session, P], R]) -> Callable[Concatenate[Session, P], R]:
    """Run a service action inside a SAVEPOINT (D-28, D-46).

    If the action raises, every change it made — including audit rows and document numbers —
    is rolled back and the session is usable again. On success the changes stay pending in
    the caller's transaction, which the caller commits (a router per request, the seed once
    at the end). Nested actions nest savepoints.
    """

    @functools.wraps(fn)
    def wrapper(db: Session, *args: P.args, **kwargs: P.kwargs) -> R:
        with db.begin_nested():
            return fn(db, *args, **kwargs)

    return wrapper
