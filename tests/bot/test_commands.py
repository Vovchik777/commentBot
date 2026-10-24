from datetime import datetime, timedelta

import pytest

from src.bot.handlers.commands import MessageHandler
from src.database.models import CommentTypes, PermissionLevel
from src.shared.time_utils import get_moscow_date
from tests.bot.fakes import FakeBot, add_user, make_message

GROUP = -100500
LOGGER_CHAT = -100555


@pytest.fixture
def env(db_manager):
    bot = FakeBot(db_manager)
    return bot, MessageHandler(bot)


def _texts(bot):
    return "\n".join(bot.texts)


# --- роутинг ---------------------------------------------------------------


def test_parse_command_strips_bot_suffix():
    handler = MessageHandler(FakeBot.__new__(FakeBot))
    assert handler._parse_command("/help@tvoyatec_bot") == "/help"
    assert handler._parse_command("/helpme") == "/helpme"
    assert handler._parse_command("привет") is None


def test_handle_command_unknown_returns_false(env):
    bot, handler = env
    assert handler.handle_command(make_message(GROUP, 1, "/nope")) is False
    assert bot.calls == []


def test_handle_command_rejects_group_only_command_in_private(env):
    bot, handler = env
    assert handler.handle_command(make_message(1, 1, "/register", chat_type="private"))
    assert "не могу выполнить в лс" in bot.last


def test_process_message_routes_group_and_private(env, monkeypatch):
    bot, handler = env
    seen = []
    monkeypatch.setattr(handler, "handle_group_message", lambda md: seen.append("group"))
    monkeypatch.setattr(handler, "handle_private_message", lambda md: seen.append("private"))

    handler.process_message(make_message(GROUP, 1, "текст"))
    handler.process_message(make_message(1, 1, "текст", chat_type="private"))

    assert seen == ["group", "private"]


def test_process_message_ignored_chat(env):
    bot, handler = env
    bot.config.IGNORING_CHAT_IDS = [str(GROUP)]

    handler.process_message(make_message(GROUP, 1, "текст"))

    assert "я не буду здесь работать" in _texts(bot)


# --- регистрация и права ---------------------------------------------------


def test_register_first_user_is_dev_and_second_is_base(env):
    bot, handler = env

    handler.handle_register(make_message(GROUP, 1, "/register", username="first"))
    handler.handle_register(make_message(GROUP, 2, "/register", username="second"))

    assert bot.db.get_user(1, GROUP).permission is PermissionLevel.DEV
    assert bot.db.get_user(2, GROUP).permission is PermissionLevel.BASE
    assert "Новый пользователь: @second" in _texts(bot)


def test_register_twice_reports_already_registered(env):
    bot, handler = env
    handler.handle_register(make_message(GROUP, 1, "/register"))

    handler.handle_register(make_message(GROUP, 1, "/register"))

    assert "Вы уже зарегистрированы" in bot.last


def test_register_anonymous_admin_gets_generated_username(env):
    bot, handler = env

    handler.handle_register(make_message(GROUP, 1087968824, "/register", username="GroupAnonymousBot"))

    user = bot.db.get_user(1087968824, GROUP)
    assert user.username.startswith("AnonymousAdmin_")
    assert user.permission is PermissionLevel.DEV


def test_unregister_removes_user(env):
    bot, handler = env
    add_user(bot.db, GROUP, 1)

    handler.handle_unregister(make_message(GROUP, 1, "/unregister"))

    assert bot.db.get_user(1, GROUP) is None
    assert "успешно удалены" in bot.last


def test_get_users_list_empty_and_filled(env):
    bot, handler = env
    handler.handle_get_users_list(make_message(GROUP, 1, "/get_users_list"))
    assert "пока нет зарегистрированных" in bot.last

    add_user(bot.db, GROUP, 1)
    add_user(bot.db, GROUP, 2)
    handler.handle_get_users_list(make_message(GROUP, 1, "/get_users_list"))
    assert "@u1" in bot.last and "@u2" in bot.last


# --- комментарии -----------------------------------------------------------


def test_add_comment_requires_moder(env):
    bot, handler = env
    add_user(bot.db, GROUP, 1, PermissionLevel.BASE)

    handler.handle_add_comment(make_message(GROUP, 1, "/add_comment text привет"))

    assert "недостаточно прав" in bot.last


def test_add_comment_saves_and_reports_duplicate(env):
    bot, handler = env
    add_user(bot.db, GROUP, 1, PermissionLevel.MODER)

    handler.handle_add_comment(make_message(GROUP, 1, "/add_comment text привет"))
    handler.handle_add_comment(make_message(GROUP, 1, "/add_comment text привет"))

    assert "Добавлен" in bot.texts[-2]
    assert "уже существует" in bot.last


def test_add_comment_rejects_bad_type_and_short_command(env):
    bot, handler = env
    add_user(bot.db, GROUP, 1, PermissionLevel.MODER)

    handler.handle_add_comment(make_message(GROUP, 1, "/add_comment video текст"))
    handler.handle_add_comment(make_message(GROUP, 1, "/add_comment text"))

    assert bot.texts[-2].startswith("Неверный тип")
    assert "Используйте /add_comment" in bot.last


def test_delete_comment_by_index(env):
    bot, handler = env
    add_user(bot.db, GROUP, 1, PermissionLevel.MODER)
    handler.handle_add_comment(make_message(GROUP, 1, "/add_comment text удалить меня"))

    handler.handle_delete_comment(make_message(GROUP, 1, "/delete_comment text 1"))
    handler.handle_delete_comment(make_message(GROUP, 1, "/delete_comment text 1"))

    assert "удален" in bot.texts[-2]
    assert "не найден" in bot.last


def test_schedule_comment_accepts_future_and_rejects_past(env):
    bot, handler = env
    add_user(bot.db, GROUP, 1, PermissionLevel.DEV)
    future = (datetime.strptime(get_moscow_date(), "%Y-%m-%d") + timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )

    handler.handle_set_schedule_comment(make_message(GROUP, 1, f"/set_schedule_comment {future} план"))
    handler.handle_set_schedule_comment(make_message(GROUP, 1, "/set_schedule_comment 2020-01-01 старое"))
    handler.handle_set_schedule_comment(make_message(GROUP, 1, "/set_schedule_comment завтра текст"))

    assert f"добавлен на дату {future}" in bot.texts[-3]
    assert "Дата должна быть строго" in bot.texts[-2]
    assert "Дата должна быть строго" in bot.texts[-1]
    scheduled = bot.comments_manager.get_comments_list(GROUP)[CommentTypes.SCHEDULED.value]
    items = list(scheduled.values())[0]
    assert items[0].comment_text == "план"


# --- /answer ---------------------------------------------------------------


def test_answer_ignores_other_chats(env):
    bot, handler = env

    handler.handle_answer(make_message(GROUP, 1, "/answer текст"))

    assert bot.calls == []


def test_answer_reports_missing_log_and_missing_text(env):
    bot, handler = env

    handler.handle_answer({**make_message(LOGGER_CHAT, 1, "/answer"), "reply_to_message": {"message_id": 900}})
    handler.handle_answer({**make_message(LOGGER_CHAT, 1, "/answer текст"), "reply_to_message": {"message_id": 901}})

    assert len(bot.texts) == 2
    assert all("не найдено в логах" in t for t in bot.texts)


def test_answer_sends_text_to_original_chat(env):
    bot, handler = env
    bot.logs_manager.info[900] = {"chat_id": GROUP, "message_id": 5}

    handler.handle_answer(
        {**make_message(LOGGER_CHAT, 1, "/answer привет"), "reply_to_message": {"message_id": 900}}
    )

    assert bot.calls[-2] == {
        "chat_id": GROUP,
        "text": "привет",
        "reply_to_message_id": 5,
        "reply_markup": None,
        "escape": False,
    }
    assert bot.last == "Ответ отправлен"


# --- прочее ----------------------------------------------------------------


def test_start_differs_for_private_and_group(env):
    bot, handler = env

    handler.handle_start(make_message(GROUP, 1, "/start"))
    handler.handle_start(make_message(1, 1, "/start", chat_type="private"))

    assert "напиши /register" in bot.texts[-2]
    assert "привет, я бот для комментов" in bot.last


def test_admin_msg_button_points_to_base_url(env):
    bot, handler = env

    handler.handle_admin_msg(make_message(GROUP, 1, "/admin_msg"))

    button = bot.calls[-1]["reply_markup"]["inline_keyboard"][0][0]
    assert button["url"] == "http://test/admin_msg"
