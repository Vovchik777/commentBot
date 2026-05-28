import pytest
import json
import tempfile
import os
from src.bot.services.comments import CommentsManager

@pytest.fixture
def temp_comments_file():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    test_data = {
        "group_123456": {
            "text": ["Первый комментарий", "Второй комментарий"],
            "photo": ["Крутое фото!", "Отличный снимок"],
            "scheduled": {"2024-01-01": ["С Новым годом!"], "2024-12-25": ["С Рождеством!"]},
        }
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(test_data, f, ensure_ascii=False)
    yield path
    if os.path.exists(path): os.remove(path)

@pytest.fixture
def empty_comments_file():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    yield path
    if os.path.exists(path): os.remove(path)

@pytest.fixture
def comments_manager(temp_comments_file):
    return CommentsManager(temp_comments_file)

class TestCommentsManager:
    def test_init_with_existing_file(self, comments_manager):
        assert "group_123456" in comments_manager.comment_data

    def test_init_with_new_file(self, empty_comments_file):
        manager = CommentsManager(empty_comments_file)
        assert manager.comment_data == {}

    def test_faker_initialization(self, empty_comments_file):
        manager = CommentsManager(empty_comments_file)
        assert manager.faker is not None
        assert "name" in manager.faker_replace

    def test_init_group_comments(self, empty_comments_file):
        manager = CommentsManager(empty_comments_file)
        manager.init_group_comments(-100123456789)
        assert "group_100123456789" in manager.comment_data

    def test_add_comment_text(self, comments_manager):
        assert comments_manager.add_comment("text", "Новый тест", 123456) is True
        assert "Новый тест" in comments_manager.comment_data["group_123456"]["text"]

    def test_add_duplicate_comment(self, comments_manager):
        assert comments_manager.add_comment("text", "Первый комментарий", 123456) is False

    def test_delete_comment_text(self, comments_manager):
        assert comments_manager.delete_comment(123456, "text", 1) == "Первый комментарий"
        assert len(comments_manager.comment_data["group_123456"]["text"]) == 1

    def test_delete_scheduled_comment(self, comments_manager):
        assert comments_manager.delete_comment(123456, "scheduled", 1) == "С Новым годом!"
        assert "2024-01-01" not in comments_manager.comment_data["group_123456"]["scheduled"]

    def test_get_random_comment(self, comments_manager):
        c = comments_manager.get_random_comment(123456, "text")
        assert c in ["Первый комментарий", "Второй комментарий"]

    def test_parse_comment_template(self, comments_manager):
        res = comments_manager.parse_comment_template("Привет, {{name}}!")
        assert "Привет, " in res and "{{name}}" not in res
