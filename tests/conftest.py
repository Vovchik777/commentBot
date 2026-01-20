import pytest
import tempfile
import json
import os


@pytest.fixture
def mock_config():
    """Мок конфигурации для тестов"""

    class MockConfig:
        BOT_TOKEN = "test_token"
        DB_FILE = ":memory:"  # Используем базу в памяти для тестов
        COMMENTS_FILE = "test_comments.json"
        LOGGED_MSGS_FILE = "test_logs.json"
        LOGGER_CHAT_ID = "123456789"
        BASE_URL = "https://test-bot.example.com"
        IGNORING_CHAT_IDS = ["999999999"]

    return MockConfig()


@pytest.fixture
def sample_message_data():
    """Тестовые данные сообщения"""
    return {
        "message_id": 123,
        "from": {
            "id": 123456,
            "first_name": "Test",
            "last_name": "User",
            "username": "testuser",
        },
        "chat": {"id": -100123456789, "type": "supergroup", "title": "Test Group"},
        "date": 1609459200,
        "text": "/test",
    }


@pytest.fixture
def sample_forwarded_message():
    """Тестовые данные пересланного сообщения"""
    return {
        "message_id": 124,
        "from": {
            "id": 123456,
            "first_name": "Test",
            "last_name": "User",
            "username": "testuser",
        },
        "chat": {"id": -100123456789, "type": "supergroup", "title": "Test Group"},
        "date": 1609459200,
        "forward_from_chat": {
            "id": -100987654321,
            "type": "channel",
            "title": "Test Channel",
        },
        "forward_date": 1609459100,
        "text": "Forwarded message text",
    }


@pytest.fixture
def sample_private_message():
    """Тестовые данные приватного сообщения"""
    return {
        "message_id": 125,
        "from": {
            "id": 123456,
            "first_name": "Test",
            "last_name": "User",
            "username": "testuser",
        },
        "chat": {
            "id": 123456,
            "type": "private",
            "first_name": "Test",
            "last_name": "User",
            "username": "testuser",
        },
        "date": 1609459200,
        "text": "Hello bot",
    }
