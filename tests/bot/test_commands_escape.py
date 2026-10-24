from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from src.bot.handlers.commands import MessageHandler
from src.bot.services.comments import CommentsManager
from src.database.models import Comment, CommentTypes, PermissionLevel, User
from src.shared.time_utils import get_moscow_date


class FakeLogsManager:
    def __init__(self):
        self.entries = []

    def get_bot_message_info(self, message_id):
        return {}

    def add_message_log(self, bot_msg_id, chat_id, message_id, text):
        self.entries.append({"bot_msg_id": bot_msg_id, "chat_id": chat_id, "text": text})


class FakeBot:
    def __init__(self, db, config):
        self.db = db
        self.config = config
        self.comments_manager = CommentsManager(db)
        self.logs_manager = FakeLogsManager()
        self.calls = []

    def get_chat_info(self, chat_id):
        return {}

    def send_message(
        self,
        chat_id,
        text,
        reply_to_message_id=None,
        reply_markup=None,
        parse_mode="HTML",
        escape=False,
    ):
        self.calls.append(
            {
                "chat_id": chat_id,
                "text": text,
                "escape": escape,
                "reply_markup": reply_markup,
            }
        )
        return {"ok": True, "result": {"message_id": len(self.calls)}}

    @property
    def last(self):
        return self.calls[-1]["text"] if self.calls else None


@pytest.fixture
def env(db_manager):
    config = SimpleNamespace(LOGGER_CHAT_ID="0", BASE_URL="http://test", IGNORING_CHAT_IDS=[])
    bot = FakeBot(db_manager, config)
    return bot, MessageHandler(bot)


def _add(db, group_id, user_id, level):
    return db.add_user(
        User(tg_group_id=group_id, tg_user_id=user_id, username=f"u{user_id}", permission=level)
    )


def _msg(chat_id, user_id, text):
    return {
        "chat": {"id": chat_id, "type": "group"},
        "from": {"id": user_id},
        "text": text,
        "message_id": 42,
    }


def _tomorrow():
    today = datetime.strptime(get_moscow_date(), "%Y-%m-%d")
    return (today + timedelta(days=1)).date().isoformat()


def test_get_banwords_escapes_values_but_keeps_bold(env):
    bot, handler = env
    _add(bot.db, -100, 999, PermissionLevel.BASE)
    bot.db.add_banword(-100, "<b>&", "a < b & c")

    handler.handle_get_banwords(_msg(-100, 999, "/get_banwords"))

    assert bot.last == "<b>&lt;b&gt;&amp;</b> - a &lt; b &amp; c\n"
    assert bot.calls[-1]["escape"] is False


def test_list_comment_escapes_text_comments(env):
    bot, handler = env
    _add(bot.db, -100, 999, PermissionLevel.BASE)
    bot.db.add_comment(Comment(-100, CommentTypes.TEXT, "a < b & c"))

    handler.handle_list_comment(_msg(-100, 999, "/comment_list"))

    assert "a &lt; b &amp; c" in bot.last
    # без escape=True, иначе длинный список вернёт too_long вместо чанков
    assert bot.calls[-1]["escape"] is False


def test_list_comment_escapes_scheduled_comments(env):
    bot, handler = env
    _add(bot.db, -100, 999, PermissionLevel.BASE)
    bot.db.add_comment(Comment(-100, CommentTypes.SCHEDULED, "a < b & c", _tomorrow()))

    handler.handle_list_comment(_msg(-100, 999, "/comment_list"))

    assert "a &lt; b &amp; c" in bot.last


def test_add_comment_confirmation_escaped(env):
    bot, handler = env
    _add(bot.db, -100, 999, PermissionLevel.MODER)

    handler.handle_add_comment(_msg(-100, 999, "/add_comment text a < b & c"))

    assert bot.last == "Добавлен text-комментарий: a &lt; b &amp; c"


def test_delete_comment_confirmation_escaped(env):
    bot, handler = env
    _add(bot.db, -100, 999, PermissionLevel.MODER)
    bot.db.add_comment(Comment(-100, CommentTypes.TEXT, "a < b & c"))

    handler.handle_delete_comment(_msg(-100, 999, "/delete_comment text 1"))

    assert bot.last == "Комментарий №1 (a &lt; b &amp; c) удален"


def test_scheduled_add_confirmation_escaped(env):
    bot, handler = env
    _add(bot.db, -100, 999, PermissionLevel.DEV)
    date = _tomorrow()

    handler.handle_set_schedule_comment(_msg(-100, 999, f"/set_schedule_comment {date} a < b & c"))

    assert bot.last == f"Комментарий <code>a &lt; b &amp; c</code> добавлен на дату {date}"


def test_admin_msg_button_typo_fixed(env):
    bot, handler = env
    _add(bot.db, -100, 999, PermissionLevel.BASE)

    handler.handle_admin_msg(_msg(-100, 999, "/admin_msg"))

    button = bot.calls[-1]["reply_markup"]["inline_keyboard"][0][0]
    assert button["text"] == "СООБЩЕНИЕ АДМИНУ"


def test_log_group_message_escapes_and_stores(env):
    bot, handler = env
    message = _msg(-100, 999, "a < b & <b>жо<па</b>")
    message["sender_chat"] = {"id": -100, "title": "Чат <&>", "type": "supergroup"}

    handler._log_group_message(message, False)

    sent = bot.calls[-1]["text"]
    assert bot.calls[-1]["chat_id"] == bot.config.LOGGER_CHAT_ID
    assert "Чат &lt;&amp;&gt;" in sent
    assert "a &lt; b &amp; &lt;b&gt;жо&lt;па&lt;/b&gt;" in sent
    # запись в логи сохранена, иначе /answer не найдёт это сообщение
    assert bot.logs_manager.entries


def test_log_private_message_escapes_text(env):
    bot, handler = env

    handler._log_private_message(_msg(-100, 999, "a < b & c"))

    assert "a &lt; b &amp; c" in bot.calls[-1]["text"]
    assert bot.logs_manager.entries
