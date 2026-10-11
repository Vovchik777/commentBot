from types import SimpleNamespace

import pytest

from src.bot.handlers.commands import MessageHandler
from src.database.models import PermissionLevel, User


class FakeBot:
    def __init__(self, db, config):
        self.db = db
        self.config = config
        self.sent = []
        self.chats = {}

    def send_message(
        self, chat_id, text, reply_to_message_id=None, reply_markup=None, parse_mode="HTML"
    ):
        self.sent.append(text)
        return {"ok": True, "result": {"message_id": len(self.sent)}}

    def get_chat_info(self, chat_id):
        return self.chats.get(chat_id, {})

    @property
    def last(self):
        return self.sent[-1] if self.sent else None


@pytest.fixture
def env(db_manager):
    config = SimpleNamespace(LOGGER_CHAT_ID="0", BASE_URL="http://test", IGNORING_CHAT_IDS=[])
    bot = FakeBot(db_manager, config)
    handler = MessageHandler(bot)
    return bot, handler


def _add(db, group_id, user_id, username, level=PermissionLevel.DEV):
    return db.add_user(
        User(tg_group_id=group_id, tg_user_id=user_id, username=username, permission=level)
    )


def _msg(chat_id, chat_type, user_id, text):
    return {
        "chat": {"id": chat_id, "type": chat_type},
        "from": {"id": user_id},
        "text": text,
        "message_id": 42,
    }


def test_usage_when_no_identifier(env):
    bot, handler = env
    _add(bot.db, -100, 999, "dev")

    handler.handle_get_user_info(_msg(-100, "group", 999, "/get_user_info"))

    assert "Используйте" in bot.last


def test_group_username_registered(env):
    bot, handler = env
    _add(bot.db, -100, 999, "dev")
    _add(bot.db, -100, 777, "target")
    bot.chats[777] = {"id": 777, "username": "target", "first_name": "Т"}

    handler.handle_get_user_info(_msg(-100, "group", 999, "/get_user_info target"))

    assert "Данные по пользователю @target" in bot.last
    assert "Права в этой группе" in bot.last


def test_group_username_not_in_group(env):
    bot, handler = env
    _add(bot.db, -100, 999, "dev")
    _add(bot.db, -200, 777, "target")

    handler.handle_get_user_info(_msg(-100, "group", 999, "/get_user_info target"))

    assert bot.last == "Пользователь не зарегистрирован в этой группе"


def test_group_username_with_at_sign_finds_user(env):
    bot, handler = env
    _add(bot.db, -100, 999, "dev")
    _add(bot.db, -100, 777, "target")
    bot.chats[777] = {"id": 777, "username": "target"}

    handler.handle_get_user_info(_msg(-100, "group", 999, "/get_user_info @target"))

    assert "Права в этой группе" in bot.last
    assert "Данные по пользователю @target" in bot.last
    assert "@@target" not in bot.last


def test_private_username_lists_all_groups(env):
    bot, handler = env
    _add(bot.db, 555, 999, "dev")
    _add(bot.db, -100, 777, "target")
    _add(bot.db, -200, 777, "target")
    bot.chats[777] = {"id": 777, "username": "target"}
    bot.chats[-100] = {"title": "GroupA"}
    bot.chats[-200] = {"title": "GroupB"}

    handler.handle_get_user_info(_msg(555, "private", 999, "/get_user_info target"))

    assert "Найден в 2 группе(ах):" in bot.last
    assert "GroupA" in bot.last
    assert "GroupB" in bot.last


def test_private_unknown_username(env):
    bot, handler = env
    _add(bot.db, 555, 999, "dev")

    handler.handle_get_user_info(_msg(555, "private", 999, "/get_user_info ghost"))

    assert bot.last == "Пользователь не найден"


def test_private_chat_id(env):
    bot, handler = env
    _add(bot.db, 555, 999, "dev")
    bot.chats[4242] = {"id": 4242, "username": "chan", "type": "channel"}

    handler.handle_get_user_info(_msg(555, "private", 999, "/get_user_info 4242"))

    assert "Данные по чату 4242" in bot.last
    assert "Права в этой группе" not in bot.last


def test_group_chat_id_shows_permission(env):
    bot, handler = env
    _add(bot.db, -100, 999, "dev")
    bot.chats[4242] = {"id": 4242, "username": "u"}

    handler.handle_get_user_info(_msg(-100, "group", 999, "/get_user_info 4242"))

    assert "Данные по чату 4242" in bot.last
    assert "Пользователь не зарегистрирован в этой группе" in bot.last


def test_group_chat_id_registered_user_shows_permission(env):
    bot, handler = env
    _add(bot.db, -100, 999, "dev")
    _add(bot.db, -100, 4242, "member", level=PermissionLevel.MODER)
    bot.chats[4242] = {"id": 4242, "username": "member"}

    handler.handle_get_user_info(_msg(-100, "group", 999, "/get_user_info 4242"))

    assert "Данные по чату 4242" in bot.last
    assert "Права в этой группе: модер" in bot.last


def test_missing_chat_info_reports_error(env):
    bot, handler = env
    _add(bot.db, -100, 999, "dev")

    handler.handle_get_user_info(_msg(-100, "group", 999, "/get_user_info 4242"))

    assert bot.last == "Не удалось получить информацию"
