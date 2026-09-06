"""Guard pytest from writing into the developer's persistent SQLite file."""

from pathlib import Path

from app.api import documents as documents_api
from app.main import DEFAULT_DB_PATH, app_store


def test_pytest_application_store_is_not_the_developer_database() -> None:
    assert Path(app_store.path).resolve() != DEFAULT_DB_PATH.resolve()


def test_pytest_documents_do_not_use_the_developer_upload_directory() -> None:
    assert documents_api._storage is not None
    default_upload_root = Path(documents_api.__file__).resolve().parents[2] / "data" / "uploads"
    assert documents_api._storage.root != default_upload_root.resolve()
