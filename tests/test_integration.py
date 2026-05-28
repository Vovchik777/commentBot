import pytest
from unittest.mock import Mock, patch
import tempfile
import os
import sys

# Гарантируем видимость src/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.bot.core import TelegramBot
from src.bot.services.comments import CommentsManager
from src.database.repository import DataBaseManager

class TestIntegration:
    def test_bot_initialization(self, mock_config):
        with patch("src.bot.core.DataBaseManager") as db,              patch("src.bot.core.CommentsManager") as cm,              patch("src.bot.core.LogsManager") as lm:
            db.return_value = Mock()
            cm.return_value = Mock()
            lm.return_value = Mock()
            bot = TelegramBot(mock_config)
            assert bot.config == mock_config
            assert hasattr(bot, "handler")

    @patch("src.bot.core.requests.post")
    def test_send_message_success(self, mock_post, mock_config):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 123}}
        mock_post.return_value = mock_resp
        
        bot = TelegramBot(mock_config)
        res = bot.send_message(chat_id=-100123456789, text="Test")
        assert mock_post.called and res["ok"] is True

    @patch("src.bot.core.requests.post")
    def test_set_message_reaction(self, mock_post, mock_config):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp
        
        bot = TelegramBot(mock_config)
        res = bot.set_message_reaction(chat_id=-100123456789, message_id=123)
        assert mock_post.called and res["ok"] is True

    def test_comment_workflow_integration(self, mock_config):
        # Создаем временные файлы
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as cf:
            comments_file = cf.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as df:
            db_file = df.name

        try:
            mock_config.COMMENTS_FILE = comments_file
            mock_config.DB_FILE = db_file
            
            db_manager = DataBaseManager(db_file)
            cm = CommentsManager(comments_file)
            
            with patch("src.bot.core.DataBaseManager", return_value=db_manager),                  patch("src.bot.core.CommentsManager", return_value=cm),                  patch("src.bot.core.LogsManager"):
                
                bot = TelegramBot(mock_config)
                assert cm.add_comment("text", "IntTest", -100123456789) is True
                rand = cm.get_random_comment(-100123456789, "text")
                assert rand in ["IntTest", "круто"]
        finally:
            # 🔧 КРИТИЧНО: Принудительно освобождаем файлы перед удалением (Windows)
            for obj_name in ["db_manager", "cm"]:
                if obj_name in locals():
                    del locals()[obj_name]
            
            for f in [comments_file, db_file]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except PermissionError:
                        pass
