import pytest
import sqlite3
from src.database.repository import DataBaseManager




@pytest.fixture(scope="function")
def temp_db_path(tmp_path):
    db_file = tmp_path / "test.db"
    return str(db_file)

@pytest.fixture(scope="function")
def db_manager(temp_db_path):
    manager = DataBaseManager(db_file=temp_db_path)
    return manager

@pytest.fixture(scope="function")
def db_cursor(temp_db_path):
    conn = sqlite3.connect(temp_db_path)
    cursor = conn.cursor()
    yield cursor
    conn.close()


@pytest.fixture
def user_factory():
    from src.database.models import User, PermissionLevel
    def _make_user(tg_group_id = 12313123, tg_user_id=777, username="default",permission = PermissionLevel.BASE):
        return User(tg_group_id=tg_group_id, tg_user_id=tg_user_id, username=username, permission=permission)
    return _make_user