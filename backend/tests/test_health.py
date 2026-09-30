import sqlite3

from app.config import get_settings


def test_health_returns_ok(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_does_not_create_schema(client):
    """Alembic owns the schema; startup only checks connectivity."""
    database_path = get_settings().database_url.removeprefix("sqlite+aiosqlite:///")

    with sqlite3.connect(database_path) as connection:
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()

    assert tables == []
