import pytest
from unittest.mock import Mock, patch
from src.bot.utils.permissions import required_permission
from src.database.models import PermissionLevel


class TestPermissionsDecorator:
    def test_required_permission_success(self):
        mock_func = Mock(return_value="Success")
        decorator = required_permission(PermissionLevel.BASE)
        decorated = decorator(mock_func)

        self_mock = Mock()
        self_mock.bot.db.get_user.return_value = Mock(permission=PermissionLevel.ADMIN)
        self_mock._send_insufficient_permissions = Mock()
        self_mock._send_user_not_found = Mock()

        msg = {"chat": {"id": -100123456789}, "from": {"id": 123456}}
        assert decorated(self_mock, msg) == "Success"
        mock_func.assert_called_once()

    def test_required_permission_insufficient(self):
        mock_func = Mock()
        decorator = required_permission(PermissionLevel.ADMIN)
        decorated = decorator(mock_func)

        self_mock = Mock()
        self_mock.bot.db.get_user.return_value = Mock(permission=PermissionLevel.BASE)
        self_mock._send_insufficient_permissions = Mock()

        decorated(self_mock, {"chat": {"id": 1}, "from": {"id": 1}})
        mock_func.assert_not_called()
        self_mock._send_insufficient_permissions.assert_called_once()

    def test_required_permission_user_not_found_blocks_admin(self):
        # Исправлено: тест теперь проверяет реальную логику декоратора
        mock_func = Mock()
        decorator = required_permission(PermissionLevel.ADMIN)
        decorated = decorator(mock_func)

        self_mock = Mock()
        self_mock.bot.db.get_user.return_value = None
        self_mock._send_user_not_found = Mock()

        decorated(self_mock, {"chat": {"id": 1}, "from": {"id": 1}})
        mock_func.assert_not_called()
        self_mock._send_user_not_found.assert_called_once()

    def test_required_permission_user_not_found_allows_base(self):
        mock_func = Mock(return_value="OK")
        decorator = required_permission(PermissionLevel.BASE)
        decorated = decorator(mock_func)

        self_mock = Mock()
        self_mock.bot.db.get_user.return_value = None

        assert decorated(self_mock, {"chat": {"id": 1}, "from": {"id": 1}}) == "OK"
        mock_func.assert_called_once()

    def test_required_permission_exception(self):
        mock_func = Mock()
        decorator = required_permission(PermissionLevel.BASE)
        decorated = decorator(mock_func)

        self_mock = Mock()
        self_mock.bot.db.get_user.side_effect = Exception("DB Error")
        self_mock._send_permission_error = Mock()

        decorated(self_mock, {"chat": {"id": 1}, "from": {"id": 1}})
        mock_func.assert_not_called()
        self_mock._send_permission_error.assert_called_once()
