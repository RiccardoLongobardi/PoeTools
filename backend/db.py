"""Database setup: SQLAlchemy engine, session factory, declarative base.

Il DB è SQLite, file singolo. Zero ops, sufficient per uso personale.

Usage:
    from backend.db import get_session, init_db

    init_db()                 # crea schema da Base.metadata (idempotente)
    with get_session() as s:
        s.add(row)
        s.commit()
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import settings


class Base(DeclarativeBase):
    """Base SQLAlchemy dichiarativa per tutti i modelli."""


# `future=True` è default in SA 2.x ma lo metto esplicito per chiarezza.
# `check_same_thread=False` è necessario perché APScheduler e FastAPI
# potrebbero toccare il DB da thread diversi.
engine = create_engine(
    settings.db_url,
    echo=settings.debug,
    future=True,
    connect_args={"check_same_thread": False} if settings.db_url.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def init_db() -> None:
    """Crea tutte le tabelle se non esistono. Idempotente."""
    # Import inside function per evitare circular import.
    # Models si registrano su Base quando il modulo viene importato.
    from backend import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager per una sessione DB.

    Commit/rollback automatico su exit; la sessione viene chiusa.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
