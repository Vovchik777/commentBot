import pytest
import json
import tempfile
import os
from unittest.mock import patch, MagicMock
from services.commentManager import CommentsManager


@pytest.fixture
def temp_comments_file():
    """Создание временного файла комментариев"""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)

    # Инициализируем с тестовыми данными
    test_data = {
        "group_123456": {
            "text": ["Первый комментарий", "Второй комментарий"],
            "photo": ["Крутое фото!", "Отличный снимок"],
            "scheduled": {
                "2024-01-01": ["С Новым годом!"],
                "2024-12-25": ["С Рождеством!"],
            },
        }
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(test_data, f, ensure_ascii=False)

    yield path
    os.remove(path) if os.path.exists(path) else None


@pytest.fixture
def empty_comments_file():
    """Создание пустого файла комментариев"""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    yield path
    os.remove(path) if os.path.exists(path) else None


@pytest.fixture
def comments_manager(temp_comments_file):
    """Создание менеджера комментариев"""
    return CommentsManager(temp_comments_file)


class TestCommentsManager:
    """Тесты для CommentsManager"""

    def test_init_with_existing_file(self, comments_manager, temp_comments_file):
        """Тест инициализации с существующим файлом"""
        assert os.path.exists(temp_comments_file)
        assert "group_123456" in comments_manager.comment_data
        assert len(comments_manager.comment_data["group_123456"]["text"]) == 2

    def test_init_with_new_file(self, empty_comments_file):
        """Тест инициализации с новым файлом"""
        manager = CommentsManager(empty_comments_file)
        assert manager.comment_data == {}

    @patch("services.commentManager.Faker")
    def test_faker_initialization(self, mock_faker):
        """Тест инициализации Faker"""
        mock_faker_instance = MagicMock()
        mock_faker.return_value = mock_faker_instance
        mock_faker_instance.name = MagicMock(return_value="Иван Иванов")

        manager = CommentsManager("test.json")
        assert mock_faker.called

    def test_init_group_comments(self, empty_comments_file):
        """Тест инициализации комментариев для группы"""
        manager = CommentsManager(empty_comments_file)
        group_id = -100123456789

        manager.init_group_comments(group_id)

        group_name = f"group_{abs(group_id)}"
        assert group_name in manager.comment_data
        assert manager.comment_data[group_name]["text"] == ["круто"]
        assert manager.comment_data[group_name]["photo"] == ["восхитительно"]
        assert manager.comment_data[group_name]["scheduled"] == {}

    def test_add_comment_text(self, comments_manager):
        """Тест добавления текстового комментария"""
        group_id = 123456
        comment_type = "text"
        new_comment = "Новый тестовый комментарий"

        success = comments_manager.add_comment(comment_type, new_comment, group_id)
        assert success is True

        # Проверяем, что комментарий добавился
        assert new_comment in comments_manager.comment_data["group_123456"]["text"]

        # Проверяем сохранение в файл
        with open(comments_manager.comments_file, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
            assert new_comment in saved_data["group_123456"]["text"]

    def test_add_duplicate_comment(self, comments_manager):
        """Тест добавления дубликата комментария"""
        group_id = 123456
        comment_type = "text"
        existing_comment = "Первый комментарий"

        success = comments_manager.add_comment(comment_type, existing_comment, group_id)
        assert success is False  # Дубликат не должен добавляться

    def test_add_comment_to_new_group(self, empty_comments_file):
        """Тест добавления комментария в новую группу"""
        manager = CommentsManager(empty_comments_file)
        group_id = 999999

        success = manager.add_comment("text", "Тестовый комментарий", group_id)
        assert success is True

        group_name = f"group_{abs(group_id)}"
        assert group_name in manager.comment_data

    def test_delete_comment_text(self, comments_manager):
        """Тест удаления текстового комментария"""
        group_id = 123456
        comment_type = "text"

        # Удаляем первый комментарий (индекс 1 для пользователя)
        deleted = comments_manager.delete_comment(group_id, comment_type, 1)
        assert deleted == "Первый комментарий"

        # Проверяем, что остался один комментарий
        assert len(comments_manager.comment_data["group_123456"]["text"]) == 1
        assert (
            "Второй комментарий"
            in comments_manager.comment_data["group_123456"]["text"]
        )

    def test_delete_comment_photo(self, comments_manager):
        """Тест удаления фото-комментария"""
        group_id = 123456
        comment_type = "photo"

        deleted = comments_manager.delete_comment(group_id, comment_type, 1)
        assert deleted == "Крутое фото!"

    def test_delete_scheduled_comment(self, comments_manager):
        """Тест удаления запланированного комментария"""
        group_id = 123456
        comment_type = "scheduled"

        # Удаляем первый запланированный комментарий
        deleted = comments_manager.delete_comment(group_id, comment_type, 1)
        assert deleted == "С Новым годом!"

        # Проверяем, что дата удалилась, если список пуст
        assert (
            "2024-01-01"
            not in comments_manager.comment_data["group_123456"]["scheduled"]
        )
        assert (
            "2024-12-25" in comments_manager.comment_data["group_123456"]["scheduled"]
        )

    def test_delete_nonexistent_comment(self, comments_manager):
        """Тест удаления несуществующего комментария"""
        group_id = 123456

        # Несуществующий индекс
        deleted = comments_manager.delete_comment(group_id, "text", 999)
        assert deleted is None

        # Несуществующий тип
        deleted = comments_manager.delete_comment(group_id, "invalid_type", 1)
        assert deleted is None

    def test_get_random_comment(self, comments_manager):
        """Тест получения случайного комментария"""
        group_id = 123456

        # Текстовые комментарии
        text_comment = comments_manager.get_random_comment(group_id, "text")
        assert text_comment in ["Первый комментарий", "Второй комментарий"]

        # Фото-комментарии
        photo_comment = comments_manager.get_random_comment(group_id, "photo")
        assert photo_comment in ["Крутое фото!", "Отличный снимок"]

        # Для новой группы
        new_group_comment = comments_manager.get_random_comment(999999, "text")
        assert new_group_comment == "круто"  # Значение по умолчанию

    def test_parse_comment_template(self, comments_manager):
        """Тест парсинга шаблонов комментариев"""
        test_templates = [
            ("Привет, {{name}}!", r"Привет, .+!"),
            ("Адрес: {{address}}", r"Адрес: .+"),
            ("Телефон: {{phone_number}}", r"Телефон: .+"),
            ("Компания: {{company}}", r"Компания: .+"),
        ]

        for template, expected_pattern in test_templates:
            result = comments_manager.parse_comment_template(template)
            assert result != template  # Шаблон должен быть заменен
            # Проверяем, что результат соответствует ожидаемому формату
            import re

            assert re.match(expected_pattern, result) is not None

    def test_add_scheduled_comment(self, comments_manager):
        """Тест добавления запланированного комментария"""
        group_id = 123456
        date = "2024-02-14"
        comment = "С Днем Святого Валентина!"

        success = comments_manager.add_scheduled_comment(comment, group_id, date)
        assert success is True

        # Проверяем добавление
        assert date in comments_manager.comment_data["group_123456"]["scheduled"]
        assert (
            comment in comments_manager.comment_data["group_123456"]["scheduled"][date]
        )

        # Проверяем дубликат
        success_duplicate = comments_manager.add_scheduled_comment(
            comment, group_id, date
        )
        assert success_duplicate is False
