import os
from pathlib import Path
import pytest
from goodmcp.database import Database, Principal
from goodmcp.fixtures import USER_A, USER_B, VIEWER


@pytest.fixture(scope="session")
def db():
    database = Database(pool_size=1)
    yield database
    database.engine.dispose()


@pytest.fixture
def a(): return Principal(USER_A, frozenset({"hub:read", "hub:write"}))


@pytest.fixture
def b(): return Principal(USER_B, frozenset({"hub:read", "hub:write"}))


@pytest.fixture
def viewer(): return Principal(VIEWER, frozenset({"hub:read", "hub:write"}))


@pytest.fixture
def storage_root(): return Path(os.environ.get("HUB_STORAGE_ROOT", "/data"))
