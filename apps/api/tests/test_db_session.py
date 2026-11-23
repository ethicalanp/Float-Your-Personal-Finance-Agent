from app.db.session import to_sync_database_url


def test_to_sync_database_url_converts_async_sqlite_driver() -> None:
    assert to_sync_database_url("sqlite+aiosqlite:///dev.db") == "sqlite:///dev.db"


def test_to_sync_database_url_preserves_psycopg_driver() -> None:
    assert (
        to_sync_database_url("postgresql+psycopg://user:password@localhost:5432/finance")
        == "postgresql+psycopg://user:password@localhost:5432/finance"
    )
