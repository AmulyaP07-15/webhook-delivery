"""Database engine and session helpers. Works with both Postgres (default,
via docker-compose) and SQLite (handy for a quick local run with no services)."""

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    # SQLite needs this to be usable across the request/worker threads.
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)


def init_db() -> None:
    """Create tables. Importing models here ensures they are registered on the
    SQLModel metadata before create_all runs."""
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a session and closes it afterwards."""
    with Session(engine) as session:
        yield session
