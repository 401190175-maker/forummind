"""Keep every pytest process out of the developer's persistent SQLite file."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory


_pytest_database_directory = TemporaryDirectory(prefix="forummind-pytest-")
_pytest_root = Path(_pytest_database_directory.name)
os.environ["FORUMMIND_DB_PATH"] = str(
    _pytest_root / "forummind.db"
)
os.environ["FORUMMIND_STORAGE_ROOT"] = str(_pytest_root / "uploads")


def pytest_sessionfinish(session, exitstatus) -> None:
    from app.main import app_store

    app_store.close()
    _pytest_database_directory.cleanup()
