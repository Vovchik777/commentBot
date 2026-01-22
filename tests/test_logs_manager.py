import pytest
import json
import tempfile
import os
import time
from datetime import datetime, timedelta
from services.logsManager import LogsManager


@pytest.fixture
def temp_logs_file():
    """Создание временного файла логов"""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)

    # Инициализируем с тестовыми данными
    test_data = {
        "111": {
            "chat_id": 123456,
            "message_id": 100,
            "text": "Первое сообщение",
            "timestamp": "2024-01-01 12:00:00",
        },
        "222": {
            "chat_id": 654321,
            "message_id": 200,
            "text": "Второе сообщение",
            "timestamp": "2024-01-02 12:00:00",
        },
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(test_data, f, ensure_ascii=False)

    yield path
    os.remove(path) if os.path.exists(path) else None


@pytest.fixture
def corruptedfile():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)

    # Инициализируем с тестовыми данными
    test_data = "{не корректный josn}"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(test_data, f, ensure_ascii=False)

    yield path
    os.remove(path) if os.path.exists(path) else None


@pytest.fixture
def empty_logs_file():
    """Создание пустого файла логов"""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    yield path
    os.remove(path) if os.path.exists(path) else None


@pytest.fixture
def logs_manager(temp_logs_file):
    """Создание менеджера логов"""
    return LogsManager(temp_logs_file)


class TestLogsManager:
    """Тесты для LogsManager"""

    def test_init_with_existing_file(self, logs_manager, temp_logs_file):
        """Тест инициализации с существующим файлом"""
        assert os.path.exists(temp_logs_file)
        assert "111" in logs_manager.logged_msgs
        assert "222" in logs_manager.logged_msgs
        assert len(logs_manager.logged_msgs) == 2

    def test_init_with_new_file(self, empty_logs_file):
        """Тест инициализации с новым файлом"""
        manager = LogsManager(empty_logs_file)
        assert manager.logged_msgs == {}

    def test_add_message_log(self, empty_logs_file):
        """Тест добавления записи в лог"""
        manager = LogsManager(empty_logs_file)

        bot_msg_id = 333
        chat_id = 123456
        message_id = 300
        text = "Тестовое сообщение"

        manager.add_message_log(bot_msg_id, chat_id, message_id, text)

        assert str(bot_msg_id) in manager.logged_msgs
        log_entry = manager.logged_msgs[str(bot_msg_id)]
        assert log_entry["chat_id"] == chat_id
        assert log_entry["message_id"] == message_id
        assert log_entry["text"] == text

        # Проверяем сохранение в файл
        with open(empty_logs_file, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
            assert str(bot_msg_id) in saved_data

    def test_get_message_info_existing(self, logs_manager):
        """Тест получения информации о существующем сообщении"""
        log_entry = logs_manager.get_message_info(111)
        assert log_entry is not None
        assert log_entry["chat_id"] == 123456
        assert log_entry["message_id"] == 100
        assert log_entry["text"] == "Первое сообщение"

    def test_get_message_info_nonexistent(self, logs_manager):
        """Тест получения информации о несуществующем сообщении"""
        log_entry = logs_manager.get_message_info(999999)
        assert log_entry is None

    def test_cleanup_old_logs(self, temp_logs_file):
        """Тест очистки старых логов"""
        from unittest.mock import patch

        # Создаем тестовые данные со старыми timestamp
        old_timestamp = 176893696.488514  # Старая дата
        current_timestamp = 1769103862.79629  # Текущая дата

        test_data = {
            "old": {
                "chat_id": 1,
                "message_id": 1,
                "text": "Старое сообщение",
                "timestamp": old_timestamp,
            },
            "current": {
                "chat_id": 2,
                "message_id": 2,
                "text": "Текущее сообщение",
                "timestamp": current_timestamp,
            },
        }

        with open(temp_logs_file, "w", encoding="utf-8") as f:
            json.dump(test_data, f, ensure_ascii=False)

        manager = LogsManager(temp_logs_file)

        # Мокаем get_moscow_datetime_str чтобы вернуть текущую дату
        with patch(
            "services.logsManager.utils.time_utils.get_moscow_datetime_str"
        ) as mock_get_time:
            mock_get_time.return_value = current_timestamp

            # Вызываем cleanup_old_logs с моком
            removed_count = manager.cleanup_old_logs()

            # Проверяем, что старая запись удалена
            assert "old" not in manager.logged_msgs
            assert "current" in manager.logged_msgs
            assert removed_count == 1

    def test_save_logs(self, empty_logs_file):
        """Тест сохранения логов в файл"""
        manager = LogsManager(empty_logs_file)

        # Добавляем запись
        manager.logged_msgs["test"] = {
            "chat_id": 999,
            "message_id": 999,
            "text": "Тест",
            "timestamp": "2024-01-01 00:00:00",
        }

        # Сохраняем
        manager.save_logs()

        # Проверяем сохранение
        with open(empty_logs_file, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
            assert "test" in saved_data
            assert saved_data["test"]["text"] == "Тест"

    def test_load_logs_corrupted_file(self, corruptedfile):
        """Тест загрузки поврежденного файла"""
        # Создаем поврежденный JSON файл
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)

        with open(path, "w", encoding="utf-8") as f:
            f.write("{ это не валидный JSON }")

        try:
            manager = LogsManager(path)
            # Должен обработать ошибку и создать пустой словарь
            assert manager.logged_msgs == {}
        finally:
            os.remove(path) if os.path.exists(path) else None
