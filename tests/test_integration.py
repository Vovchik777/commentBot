import pytest
from unittest.mock import Mock, patch, AsyncMock
import json
import tempfile
import os


class TestIntegration:
    """Интеграционные тесты для взаимодействия компонентов"""

    def test_bot_initialization(self, mock_config):
        """Тест инициализации бота"""
        from telegram.bot import TelegramBot

        with patch("telegram.bot.DataBaseManager") as mock_db_manager, patch(
            "telegram.bot.CommentsManager"
        ) as mock_comments_manager, patch(
            "telegram.bot.LogsManager"
        ) as mock_logs_manager:

            # Создаем моки
            mock_db_instance = Mock()
            mock_comments_instance = Mock()
            mock_logs_instance = Mock()

            mock_db_manager.return_value = mock_db_instance
            mock_comments_manager.return_value = mock_comments_instance
            mock_logs_manager.return_value = mock_logs_instance

            # Инициализируем бота
            bot = TelegramBot(mock_config)

            # Проверяем инициализацию компонентов
            assert bot.config == mock_config
            assert bot.db == mock_db_instance
            assert bot.comments_manager == mock_comments_instance
            assert bot.logs_manager == mock_logs_instance
            assert hasattr(bot, "handler")

    @patch("telegram.bot.requests.post")
    def test_send_message_success(self, mock_post, mock_config):
        """Тест успешной отправки сообщения"""
        from telegram.bot import TelegramBot

        # Настраиваем мок ответа
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 123}}
        mock_post.return_value = mock_response

        # Инициализируем бота
        bot = TelegramBot(mock_config)

        # Отправляем сообщение
        result = bot.send_message(chat_id=-100123456789, text="Test message")

        # Проверяем вызов API
        assert mock_post.called
        assert result["ok"] is True

    @patch("telegram.bot.requests.post")
    def test_set_message_reaction(self, mock_post, mock_config):
        """Тест установки реакции на сообщение"""
        from telegram.bot import TelegramBot

        # Настраиваем мок ответа
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_post.return_value = mock_response

        bot = TelegramBot(mock_config)
        result = bot.set_message_reaction(chat_id=-100123456789, message_id=123)

        assert mock_post.called
        assert result["ok"] is True

    def test_comment_workflow_integration(self, mock_config):
        """Тест полного workflow работы с комментариями"""
        from telegram.bot import TelegramBot
        from services.commentManager import CommentsManager
        from database.manager import DataBaseManager

        # Создаем временные файлы
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            comments_file = f.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
            db_file = f.name

        try:
            # Обновляем конфиг
            mock_config.COMMENTS_FILE = comments_file
            mock_config.DB_FILE = db_file

            # Инициализируем компоненты
            db_manager = DataBaseManager(db_file)
            comments_manager = CommentsManager(comments_file)

            # Создаем бота с моками
            with patch("telegram.bot.DataBaseManager", return_value=db_manager), patch(
                "telegram.bot.CommentsManager", return_value=comments_manager
            ), patch("telegram.bot.LogsManager"):

                bot = TelegramBot(mock_config)

                # Тестируем добавление комментария
                group_id = -100123456789
                test_comment = "Test integration comment"

                # Добавляем комментарий через менеджер
                success = comments_manager.add_comment("text", test_comment, group_id)
                assert success is True

                # Получаем случайный комментарий
                random_comment = comments_manager.get_random_comment(group_id, "text")
                assert random_comment == test_comment

        finally:
            # Очищаем временные файлы
            if os.path.exists(comments_file):
                os.remove(comments_file)
            if os.path.exists(db_file):
                os.remove(db_file)
