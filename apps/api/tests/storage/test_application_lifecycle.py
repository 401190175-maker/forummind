"""Application database configuration tests."""

from app.main import resolve_db_path


def test_application_store_path_comes_from_environment(monkeypatch, tmp_path):
    path = tmp_path / "api.db"
    monkeypatch.setenv("FORUMMIND_DB_PATH", str(path))

    assert resolve_db_path() == path


def test_application_store_path_has_api_data_default(monkeypatch):
    monkeypatch.delenv("FORUMMIND_DB_PATH", raising=False)

    assert resolve_db_path().as_posix().endswith("apps/api/data/forummind.db")


def test_api_modules_share_the_application_store():
    from app.api import runs as runs_api
    from app.group_chats import creation_service, messages
    from app.main import app_store

    assert creation_service._persistence_store is app_store
    assert messages._persistence_store is app_store
    assert runs_api.run_store._persistence_store is app_store
