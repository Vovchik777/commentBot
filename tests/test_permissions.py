import pytest
from unittest.mock import Mock, patch, MagicMock
from telegram.permissions import required_permission
from database.models import PermissionLevel


class TestPermissionsDecorator:
    """Тесты для декоратора required_permission"""

    def test_required_permission_success(self):
        """Тест успешной проверки разрешений"""
        # Создаем мок функции
        mock_func = Mock(return_value="Success")

        # Создаем декоратор
        decorator = required_permission(PermissionLevel.BASE)
        decorated_func = decorator(mock_func)

        # Создаем мок self с необходимыми атрибутами
        mock_self = Mock()
        mock_self.bot = Mock()
        mock_self.bot.db = Mock()

        # Настраиваем возвращаемого пользователя с достаточными правами
        mock_user = Mock()
        mock_user.permission = PermissionLevel.ADMIN  # Права выше требуемых
        mock_self.bot.db.get_user.return_value = mock_user

        # Моки для вспомогательных методов
        mock_self._send_insufficient_permissions = Mock()
        mock_self._send_permission_error = Mock()
        mock_self._user_not_found = Mock()

        # Тестовые данные сообщения
        message_data = {
            "chat": {"id": -100123456789},
            "from": {"id": 123456},
            "text": "/test",
        }

        # Вызываем декорированную функцию
        result = decorated_func(mock_self, message_data)

        # Проверяем, что функция была вызвана
        assert mock_func.called
        assert result == "Success"
        mock_self._send_insufficient_permissions.assert_not_called()

    def test_required_permission_insufficient(self):
        """Тест недостаточных разрешений"""
        # Создаем мок функции
        mock_func = Mock()

        # Создаем декоратор
        decorator = required_permission(PermissionLevel.ADMIN)
        decorated_func = decorator(mock_func)

        # Создаем мок self
        mock_self = Mock()
        mock_self.bot = Mock()
        mock_self.bot.db = Mock()

        # Пользователь с недостаточными правами
        mock_user = Mock()
        mock_user.permission = PermissionLevel.BASE  # Права ниже требуемых
        mock_self.bot.db.get_user.return_value = mock_user

        # Моки вспомогательных методов
        mock_self._send_insufficient_permissions = Mock()
        mock_self._send_permission_error = Mock()
        mock_self._user_not_found = Mock()

        # Тестовые данные
        message_data = {
            "chat": {"id": -100123456789},
            "from": {"id": 123456},
            "text": "/test",
        }

        # Вызываем декорированную функцию
        decorated_func(mock_self, message_data)

        # Проверяем, что функция не была вызвана
        assert not mock_func.called
        # Проверяем, что было вызвано сообщение о недостаточных правах
        mock_self._send_insufficient_permissions.assert_called_once()

    def test_required_permission_user_not_found(self):
        """Тест ситуации, когда пользователь не найден"""
        # Создаем мок функции
        mock_func = Mock()

        # Создаем декоратор
        decorator = required_permission(PermissionLevel.BASE)
        decorated_func = decorator(mock_func)

        # Создаем мок self
        mock_self = Mock()
        mock_self.bot = Mock()
        mock_self.bot.db = Mock()

        # Пользователь не найден
        mock_self.bot.db.get_user.return_value = None

        # Моки вспомогательных методов
        mock_self._send_insufficient_permissions = Mock()
        mock_self._send_permission_error = Mock()
        mock_self._send_user_not_found = Mock()

        # Тестовые данные
        message_data = {
            "chat": {"id": -100123456789},
            "from": {"id": 123456},
            "text": "/test",
        }

        # Вызываем декорированную функцию
        decorated_func(mock_self, message_data)

        # Проверяем, что функция не была вызвана
        assert not mock_func.called
        # Проверяем, что был вызван метод для пользователя не найден
        mock_self._send_user_not_found.assert_called_once()

    def test_required_permission_exception(self):
        """Тест обработки исключений"""
        # Создаем мок функции, которая выбрасывает исключение
        mock_func = Mock()

        # Создаем декоратор
        decorator = required_permission(PermissionLevel.BASE)
        decorated_func = decorator(mock_func)

        # Создаем мок self с исключением при получении пользователя
        mock_self = Mock()
        mock_self.bot = Mock()
        mock_self.bot.db = Mock()
        mock_self.bot.db.get_user.side_effect = Exception("Database error")

        # Моки вспомогательных методов
        mock_self._send_insufficient_permissions = Mock()
        mock_self._send_permission_error = Mock()
        mock_self._send_user_not_found = Mock()

        # Тестовые данные
        message_data = {
            "chat": {"id": -100123456789},
            "from": {"id": 123456},
            "text": "/test",
        }

        # Вызываем декорированную функцию
        decorated_func(mock_self, message_data)

        # Проверяем, что функция не была вызвана
        assert not mock_func.called
        # Проверяем, что было вызвано сообщение об ошибке
        mock_self._send_permission_error.assert_called_once()

    def test_required_permission_missing_chat_id(self):
        """Тест с отсутствующим chat_id"""
        # Создаем мок функции
        mock_func = Mock()

        # Создаем декоратор
        decorator = required_permission(PermissionLevel.BASE)
        decorated_func = decorator(mock_func)

        # Создаем мок self
        mock_self = Mock()
        mock_self.bot = Mock()
        mock_self.bot.db = Mock()

        # Моки вспомогательных методов
        mock_self._send_insufficient_permissions = Mock()
        mock_self._send_permission_error = Mock()
        mock_self._user_not_found = Mock()

        # Тестовые данные без chat_id
        message_data = {"from": {"id": 123456}, "text": "/test"}

        # Вызываем декорированную функцию
        decorated_func(mock_self, message_data)

        # Проверяем, что функция не была вызвана
        assert not mock_func.called

    def test_permission_hierarchy(self):
        """Тест иерархии разрешений"""
        # Проверяем, что PermissionLevel корректно сравнивается
        assert PermissionLevel.BASE < PermissionLevel.MODER
        assert PermissionLevel.MODER < PermissionLevel.ADMIN
        assert PermissionLevel.ADMIN < PermissionLevel.DEV
        assert PermissionLevel.DEV < PermissionLevel.LOGGER

        # Проверяем операторы сравнения
        assert PermissionLevel.BASE <= PermissionLevel.BASE
        assert PermissionLevel.ADMIN >= PermissionLevel.MODER
        assert PermissionLevel.LOGGER > PermissionLevel.DEV
