import sys
import os
import pytest
import tempfile
import json

# 🔧 КРИТИЧНО: Добавляем корень проекта в sys.path ДО импортов
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

@pytest.fixture
def mock_config():
    class MockConfig:
        BOT_TOKEN = "test_token"
        DB_FILE = ":memory:"
        COMMENTS_FILE = "test_comments.json"
        LOGGED_MSGS_FILE = "test_logs.json"
        LOGGER_CHAT_ID = "123456789"
        BASE_URL = "https://test-bot.example.com"
        IGNORING_CHAT_IDS = ["999999999"]
        SECRET_TOKEN = "test_secret"
    return MockConfig()

@pytest.fixture
def sample_message_data():
    return {
        "message_id": 123,
        "from": {"id": 123456, "username": "testuser"},
        "chat": {"id": -100123456789, "type": "supergroup"},
        "text": "/test",
    }
