import pytest
import sqlite3
import tempfile
import os
from unittest.mock import Mock, patch
from database.manager import DataBaseManager
from database.models import User, PermissionLevel


@pytest.fixture
def temp_db():
    """Создание временной базы данных для тестов"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.remove(path) if os.path.exists(path) else None


@pytest.fixture
def db_manager(temp_db):
    """Создание менеджера БД"""
    return DataBaseManager(temp_db)


@pytest.fixture
def sample_user():
    """Создание тестового пользователя"""
    return User(
        user_id=123456,
        username="test_user",
        permission=PermissionLevel.BASE,
        group_id=-100123456789,
    )


class TestPermissionLevel:
    """Тесты для PermissionLevel"""

    def test_from_string_valid(self):
        """Тест преобразования строки в PermissionLevel"""
        assert PermissionLevel.from_string("base") == PermissionLevel.BASE
        assert PermissionLevel.from_string("MODER") == PermissionLevel.MODER
        assert PermissionLevel.from_string("admin") == PermissionLevel.ADMIN
        assert PermissionLevel.from_string("developer") == PermissionLevel.DEV
        assert PermissionLevel.from_string("logger") == PermissionLevel.LOGGER

    def test_from_string_invalid(self):
        """Тест невалидных значений"""
        assert PermissionLevel.from_string("invalid") is None
        assert PermissionLevel.from_string("") is None

    def test_to_string(self):
        """Тест преобразования в строку"""
        assert PermissionLevel.BASE.to_string() == "базовый минимум"
        assert PermissionLevel.MODER.to_string() == "модер"
        assert PermissionLevel.ADMIN.to_string() == "админ"
        assert PermissionLevel.DEV.to_string() == "разработчик"
        assert PermissionLevel.LOGGER.to_string() == "очень клутой"


class TestUserModel:
    """Тесты для модели User"""

    def test_user_creation(self, sample_user):
        """Тест создания пользователя"""
        assert sample_user.user_id == 123456
        assert sample_user.username == "test_user"
        assert sample_user.permission == PermissionLevel.BASE
        assert sample_user.group_id == -100123456789

    def test_table_name_property(self, sample_user):
        """Тест свойства table_name"""
        assert sample_user.table_name == "group_100123456789"


class TestDataBaseManager:
    """Тесты для DataBaseManager"""

    def test_init(self, db_manager):
        """Тест инициализации"""
        assert db_manager.db_file.endswith(".db")
        assert hasattr(db_manager, "local")

    def test_create_group_table(self, db_manager):
        """Тест создания таблицы группы"""
        group_id = -100123456789
        db_manager.create_group_table(group_id)

        # Проверяем, что таблица создана
        conn = sqlite3.connect(db_manager.db_file)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='group_100123456789'"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None

    def test_delete_user_success(self, db_manager, sample_user):
        """Тест успешного удаления пользователя"""
        # Сначала добавляем пользователя
        db_manager.add_user(sample_user)

        # Удаляем пользователя
        success = db_manager.delete_user(sample_user)
        assert success is True

        # Проверяем, что пользователь удален
        user = db_manager.get_user(sample_user.user_id, sample_user.group_id)
        assert user is None

    def test_delete_nonexistent_user(self, db_manager, sample_user):
        """Тест удаления несуществующего пользователя"""
        # Пытаемся удалить пользователя, которого нет в базе
        success = db_manager.delete_user(sample_user)
        assert success is False

    def test_add_and_get_user(self, db_manager, sample_user):
        """Тест добавления и получения пользователя"""
        # Добавляем пользователя
        success = db_manager.add_user(sample_user)
        assert success is True

        # Получаем пользователя
        user = db_manager.get_user(sample_user.user_id, sample_user.group_id)
        assert user is not None
        assert user.user_id == sample_user.user_id
        assert user.username == sample_user.username
        assert user.permission == sample_user.permission

    def test_add_duplicate_user(self, db_manager, sample_user):
        """Тест добавления дубликата пользователя"""
        success1 = db_manager.add_user(sample_user)
        success2 = db_manager.add_user(sample_user)

        assert success1 is True
        assert success2 is False  # Дубликат не должен добавляться

    def test_get_nonexistent_user(self, db_manager):
        """Тест получения несуществующего пользователя"""
        user = db_manager.get_user(999999, -100123456789)
        assert user is None

    def test_update_user_permission(self, db_manager, sample_user):
        """Тест обновления прав пользователя"""
        # Сначала добавляем
        db_manager.add_user(sample_user)

        # Обновляем права
        success = db_manager.update_user_permission(sample_user, PermissionLevel.ADMIN)
        assert success is True

        # Проверяем обновление
        user = db_manager.get_user(sample_user.user_id, sample_user.group_id)
        assert user.permission == PermissionLevel.ADMIN

    def test_get_user_by_username(self, db_manager, sample_user):
        """Тест поиска пользователя по username"""
        # Добавляем пользователя
        db_manager.add_user(sample_user)

        # Ищем по username
        user = db_manager.get_user_by_username("@test_user", sample_user.group_id)
        assert user is not None
        assert user.username == "test_user"

        # Ищем без @
        user = db_manager.get_user_by_username("test_user", sample_user.group_id)
        assert user is not None

    def test_get_all_users_in_group(self, db_manager, sample_user):
        """Тест получения всех пользователей группы"""
        # Добавляем несколько пользователей
        users_to_add = [
            sample_user,
            User(
                user_id=456,
                username="user2",
                permission=PermissionLevel.MODER,
                group_id=sample_user.group_id,
            ),
            User(
                user_id=789,
                username="user3",
                permission=PermissionLevel.ADMIN,
                group_id=sample_user.group_id,
            ),
        ]

        for user in users_to_add:
            db_manager.add_user(user)

        # Получаем всех пользователей
        users = db_manager.get_all_users_in_group(sample_user.group_id)
        assert len(users) == 3

        # Проверяем сортировку по permission DESC
        permissions = [user.permission for user in users]
        assert permissions == [
            PermissionLevel.ADMIN,
            PermissionLevel.MODER,
            PermissionLevel.BASE,
        ]

    def test_get_user_by_username_across_groups(self, db_manager):
        """Тест поиска пользователя по username во всех группах"""
        # Создаем пользователей в разных группах
        user1 = User(
            user_id=111,
            username="same_name",
            permission=PermissionLevel.BASE,
            group_id=-100111,
        )
        user2 = User(
            user_id=222,
            username="same_name",
            permission=PermissionLevel.MODER,
            group_id=-100222,
        )

        db_manager.add_user(user1)
        db_manager.add_user(user2)

        # Ищем без указания группы
        found_user = db_manager.get_user_by_username("same_name")
        assert found_user is not None
        assert found_user.username == "same_name"

    def test_connection_thread_local(self, temp_db):
        """Тест thread-local соединений"""
        import threading

        def get_connection_in_thread(db_path, result_list):
            manager = DataBaseManager(db_path)
            conn = manager._get_connection()
            result_list.append(conn)

        # Запускаем в разных потоках
        results = []
        threads = []

        for i in range(3):
            thread = threading.Thread(
                target=get_connection_in_thread, args=(temp_db, results)
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Проверяем, что соединения разные
        assert len(results) == 3
        # Все соединения должны быть разными объектами (в разных потоках)
        assert results[0] != results[1] or results[1] != results[2]
