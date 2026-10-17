from types import SimpleNamespace

import pytest

from src.bot.handlers.commands import MessageHandler


class FakeBot:
    def __init__(self, db, config):
        self.db = db
        self.config = config
        self.sent = []
        self.forwarded = []
        self.banword_checked = []

    def send_message(
        self, chat_id, text, reply_to_message_id=None, reply_markup=None, parse_mode="HTML"
    ):
        self.sent.append(text)
        return {"ok": True, "result": {"message_id": len(self.sent)}}

    def get_chat_info(self, chat_id):
        return {}

    def check_banwords(self, message_data):
        self.banword_checked.append(message_data)

    def handle_forwarded_message(self, message_data):
        self.forwarded.append(message_data)

    @property
    def last(self):
        return self.sent[-1] if self.sent else None


@pytest.fixture
def env(db_manager):
    config = SimpleNamespace(LOGGER_CHAT_ID="0", BASE_URL="http://test", IGNORING_CHAT_IDS=[])
    bot = FakeBot(db_manager, config)
    handler = MessageHandler(bot)
    return bot, handler


def _private(text, user_id=111, chat_id=111):
    return {
        "chat": {"id": chat_id, "type": "private"},
        "from": {"id": user_id, "username": "tester"},
        "text": text,
        "message_id": 42,
    }


def _group(text, user_id=111, chat_id=-100):
    return {
        "chat": {"id": chat_id, "type": "supergroup"},
        "from": {"id": user_id, "username": "tester"},
        "text": text,
        "message_id": 42,
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/help", "/help"),
        ("/help@MyBot", "/help"),
        ("/HELP@somebot args", "/help"),
        ("/start@mybot", "/start"),
        ("привет", None),
        ("", None),
        (" ", None),
        ("help", None),
    ],
)
def test_parse_command(env, text, expected):
    _, handler = env
    assert handler._parse_command(text) == expected


def test_group_help_dispatched(env):
    bot, handler = env
    assert handler.handle_command(_group("/help")) is True
    assert "помощь" in bot.last


def test_group_helpme_ignored(env):
    bot, handler = env
    assert handler.handle_command(_group("/helpme")) is False
    assert bot.sent == []


def test_private_help_dispatched(env):
    bot, handler = env
    assert handler.handle_command(_private("/help")) is True
    assert "помощь" in bot.last


def test_private_group_only_command_rejected(env):
    bot, handler = env
    assert handler.handle_command(_private("/register")) is True
    assert bot.last == "не могу выполнить в лс"


def test_group_private_only_command_ignored(env):
    bot, handler = env
    assert handler.handle_command(_group("/answer")) is False
    assert bot.sent == []


def test_private_start_with_bot_suffix(env):
    bot, handler = env
    assert handler.handle_command(_private("/start@MyBot")) is True
    assert "привет, я бот для комментов" in bot.last


def test_private_non_command_echoes(env, monkeypatch):
    bot, handler = env
    monkeypatch.setattr(handler, "_log_private_message", lambda message_data: None)

    handler.process_message(_private("привет"))

    assert bot.last == "мармелад"


def test_group_command_logs_and_dispatches(env, monkeypatch):
    bot, handler = env
    logged = []
    monkeypatch.setattr(
        handler,
        "_log_group_message",
        lambda message_data, is_forwarded: logged.append(message_data),
    )

    handler.process_message(_group("/help"))

    assert "помощь" in bot.last
    assert len(logged) == 1


def test_group_non_command_skips_command_dispatch(env, monkeypatch):
    bot, handler = env
    monkeypatch.setattr(handler, "_log_group_message", lambda message_data, is_forwarded: None)

    handler.process_message(_group("обычное сообщение"))

    assert bot.sent == []
