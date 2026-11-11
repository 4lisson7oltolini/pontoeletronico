import pytest

from database.connection import get_database_url


def test_postgresql_urls_use_the_installed_psycopg_driver(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@localhost/ponto_facil")

    assert get_database_url() == "postgresql+psycopg://user:password@localhost/ponto_facil"


def test_sqlite_is_rejected_as_an_application_database(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")

    with pytest.raises(RuntimeError, match="PostgreSQL"):
        get_database_url()
