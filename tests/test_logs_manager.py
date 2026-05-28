# tests/test_logs_manager.py
import pytest
import json
import tempfile
import os
from unittest.mock import patch
from src.bot.services.logging import LogsManager


@pytest.fixture
def temp_logs_file():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    test_data = {
        "111": {"chat_id": 123456, "message_id": 100, "text": "Первое", "timestamp": 1700000000},
        "222": {"chat_id": 654321, "message_id": 200, "text": "Второе", "timestamp": 1700000000},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(test_data, f, ensure_ascii=False)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def empty_logs_file():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def logs_manager(temp_logs_file):
    return LogsManager(temp_logs_file)


class TestLogsManager:
    def test_init_with_existing_file(self, logs_manager):
        assert len(logs_manager.logged_msgs) == 2

    def test_init_with_new_file(self, empty_logs_file):
        assert LogsManager(empty_logs_file).logged_msgs == {}

    # ✅ ИСПРАВЛЕНО: Патчим функцию там, где она используется (в logging.py)
    # Путь: src.bot.services.logging.get_moscow_now
    @patch("src.bot.services.logging.get_moscow_now")
    def test_add_message_log(self, mock_time, empty_logs_file):
        mock_time.return_value = 1700000000.0
        manager = LogsManager(empty_logs_file)
        manager.add_message_log(333, 123456, 300, "Тест")
        assert "333" in manager.logged_msgs
        assert manager.logged_msgs["333"]["text"] == "Тест"

    def test_get_message_info_existing(self, logs_manager):
        assert logs_manager.get_message_info(111)["chat_id"] == 123456

    def test_get_message_info_nonexistent(self, logs_manager):
        assert logs_manager.get_message_info(999999) is None

    # ✅ ИСПРАВЛЕНО: Тот же путь, что и выше
    @patch("src.bot.services.logging.get_moscow_now")
    def test_cleanup_old_logs(self, mock_time, temp_logs_file):
        now = 1769103862.79629
        mock_time.return_value = now
        test_data = {
            "old": {"chat_id": 1, "message_id": 1, "text": "Старое", "timestamp": 176893696.4},
            "current": {"chat_id": 2, "message_id": 2, "text": "Текущее", "timestamp": now},
        }
        with open(temp_logs_file, "w", encoding="utf-8") as f:
            json.dump(test_data, f, ensure_ascii=False)

        manager = LogsManager(temp_logs_file)
        assert manager.cleanup_old_logs() == 1
        assert "old" not in manager.logged_msgs
        assert "current" in manager.logged_msgs
