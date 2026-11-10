import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH_ENV = "JOBPILOT_DATABASE_PATH"


def resolve_database_path() -> Path:
    """Return the SQLite file to use.

    ``JOBPILOT_DATABASE_PATH`` overrides the default ``jobpilot.db`` in the
    project root. It is read on every call so tests can point at a temporary
    database. This is the single place that decides which database is used.
    """
    configured = os.getenv(DATABASE_PATH_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return PROJECT_ROOT / "jobpilot.db"


DATABASE_PATH = resolve_database_path()

DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"


class Base(DeclarativeBase):
    pass


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)