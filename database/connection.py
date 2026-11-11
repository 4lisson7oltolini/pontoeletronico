"""SQLAlchemy engine and session configuration."""

from contextlib import contextmanager
from functools import lru_cache
import os
from typing import Iterator

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from streamlit.errors import StreamlitSecretNotFoundError

load_dotenv()


def get_database_url() -> str:
    """Read the database URL from the environment or Streamlit secrets."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        try:
            import streamlit as st

            database_url = st.secrets.get("DATABASE_URL")
        except (ImportError, FileNotFoundError, StreamlitSecretNotFoundError):
            database_url = None

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL não configurada. Defina-a no arquivo .env "
            "ou nos Streamlit Secrets."
        )
    url = make_url(str(database_url))
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("DATABASE_URL deve apontar para uma instância PostgreSQL.")
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create the application engine once per process."""
    return create_engine(get_database_url(), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a session and always close it after the request."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
