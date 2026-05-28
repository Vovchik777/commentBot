import pytest
import sqlite3
import tempfile
import os
from src.database.repository import DataBaseManager
from src.database.models import User, PermissionLevel

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path): os.remove(path)

@pytest.fixture
def db_manager(temp_db):
    return DataBaseManager(temp_db)

@pytest.fixture
def sample_user():
    return User(
        tg_user_id=123456,
        username="test_user",
        permission=PermissionLevel.BASE,
        tg_group_id=-100123456789,
    )

class TestDataBaseManager:
    def test_init(self, db_manager):
        assert db_manager.db_file.endswith(".db")

    def test_add_and_get_user(self, db_manager, sample_user):
        assert db_manager.add_user(sample_user) is True
        user = db_manager.get_user(sample_user.tg_user_id, sample_user.tg_group_id)
        assert user is not None and user.tg_user_id == sample_user.tg_user_id

    def test_get_user_by_username_across_groups(self, db_manager):
        # Создаем двух пользователей с одинаковым username, но в разных группах
        u1 = User(tg_user_id=111, username="same_name", permission=PermissionLevel.BASE, tg_group_id=-100111)
        u2 = User(tg_user_id=222, username="same_name", permission=PermissionLevel.MODER, tg_group_id=-100222)
        
        db_manager.add_user(u1)
        db_manager.add_user(u2)

        # Поиск без указания группы должен вернуть список
        found = db_manager.get_user_by_username("same_name")
        assert isinstance(found, list), f"Ожидался список, получен {type(found)}"
        assert len(found) >= 1, f"Ожидалось >= 1 пользователей, найдено {len(found)}"
        assert all(u.username == "same_name" for u in found)
