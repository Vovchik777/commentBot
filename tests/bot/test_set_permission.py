from types import SimpleNamespace

import pytest

from src.bot.handlers.commands import MessageHandler
from src.database.models import PermissionLevel, User


class FakeBot:
    def __init__(self, db, config):
        self.db = db
        self.config = config
        self.sent = []

    def send_message(
        self, chat_id, text, reply_to_message_id=None, reply_markup=None, parse_mode="HTML"
    ):
        self.sent.append(text)
        return {"ok": True, "result": {"message_id": len(self.sent)}}

    @property
    def last(self):
        return self.sent[-1] if self.sent else None


@pytest.fixture
def env(db_manager):
    config = SimpleNamespace(LOGGER_CHAT_ID="0", BASE_URL="http://test", IGNORING_CHAT_IDS=[])
    bot = FakeBot(db_manager, config)
    handler = MessageHandler(bot)
    return bot, handler


def _add(db, group_id, user_id, username, level=PermissionLevel.BASE):
    return db.add_user(
        User(tg_group_id=group_id, tg_user_id=user_id, username=username, permission=level)
    )


def _cmd(chat_id, user_id, text, reply=None):
    message = {
        "chat": {"id": chat_id, "type": "group"},
        "from": {"id": user_id},
        "text": text,
        "message_id": 100,
    }
    if reply is not None:
        message["reply_to_message"] = reply
    return message


def test_reply_sets_permission(env):
    bot, handler = env
    _add(bot.db, -100, 999, "admin", level=PermissionLevel.ADMIN)
    _add(bot.db, -100, 777, "target", level=PermissionLevel.BASE)

    handler.handle_set_permission(
        _cmd(-100, 999, "/set_permission moder", reply={"from": {"id": 777}, "message_id": 1})
    )

    assert "теперь имеет права модер" in bot.last
    assert bot.db.get_user(777, -100).permission == PermissionLevel.MODER


def test_reply_target_without_username(env):
    bot, handler = env
    _add(bot.db, -100, 999, "admin", level=PermissionLevel.ADMIN)
    _add(bot.db, -100, 777, "", level=PermissionLevel.BASE)

    handler.handle_set_permission(
        _cmd(-100, 999, "/set_permission admin", reply={"from": {"id": 777}, "message_id": 1})
    )

    assert "@id_777 теперь имеет права админ" in bot.last


def test_reply_without_from_reports_error(env):
    bot, handler = env
    _add(bot.db, -100, 999, "admin", level=PermissionLevel.ADMIN)

    handler.handle_set_permission(_cmd(-100, 999, "/set_permission moder", reply={"message_id": 1}))

    assert bot.last == "Не удалось определить пользователя из ответа"


def test_reply_to_unregistered_user(env):
    bot, handler = env
    _add(bot.db, -100, 999, "admin", level=PermissionLevel.ADMIN)

    handler.handle_set_permission(
        _cmd(-100, 999, "/set_permission moder", reply={"from": {"id": 777}, "message_id": 1})
    )

    assert bot.last == "Пользователь не найден"


def test_reply_invalid_permission(env):
    bot, handler = env
    _add(bot.db, -100, 999, "admin", level=PermissionLevel.ADMIN)
    _add(bot.db, -100, 777, "target", level=PermissionLevel.BASE)

    handler.handle_set_permission(
        _cmd(-100, 999, "/set_permission nope", reply={"from": {"id": 777}, "message_id": 1})
    )

    assert "Неверное значение разрешения" in bot.last


def test_username_form_still_works(env):
    bot, handler = env
    _add(bot.db, -100, 999, "admin", level=PermissionLevel.ADMIN)
    _add(bot.db, -100, 777, "target", level=PermissionLevel.BASE)

    handler.handle_set_permission(_cmd(-100, 999, "/set_permission @target moder"))

    assert "теперь имеет права модер" in bot.last
    assert bot.db.get_user(777, -100).permission == PermissionLevel.MODER


def test_username_case_insensitive(env):
    bot, handler = env
    _add(bot.db, -100, 999, "admin", level=PermissionLevel.ADMIN)
    _add(bot.db, -100, 777, "target", level=PermissionLevel.BASE)

    handler.handle_set_permission(_cmd(-100, 999, "/set_permission @TARGET moder"))

    assert bot.db.get_user(777, -100).permission == PermissionLevel.MODER


def test_usage_message_mentions_reply(env):
    bot, handler = env
    _add(bot.db, -100, 999, "admin", level=PermissionLevel.ADMIN)

    handler.handle_set_permission(_cmd(-100, 999, "/set_permission"))

    assert "ответьте на сообщение" in bot.last
