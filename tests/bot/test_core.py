from types import SimpleNamespace

import pytest
import requests

from src.bot import core as core_module
from src.bot.core import TelegramBot
from src.config import Config


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = {"ok": True, "result": {}} if payload is None else payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture
def bot(temp_db_path):
    config = Config(BOT_TOKEN="123:TESTTOKEN", LOGGER_CHAT_ID="0", DB_FILE=temp_db_path)
    return TelegramBot(config)


@pytest.fixture
def http(monkeypatch):
    state = SimpleNamespace(responses=[], calls=[], sleeps=[])

    def fake_post(url, json=None, timeout=None):
        state.calls.append(dict(json))
        if not state.responses:
            raise AssertionError("неожиданный HTTP-вызов")
        resp = state.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    monkeypatch.setattr(core_module.requests, "post", fake_post)
    monkeypatch.setattr(core_module, "time", SimpleNamespace(sleep=state.sleeps.append))
    return state


def _429(retry_after=0):
    return FakeResponse(429, {"ok": False, "parameters": {"retry_after": retry_after}})


def test_reaction_ok_first_try(bot, http):
    http.responses = [FakeResponse(200, {"ok": True, "result": True})]

    result = bot.set_message_reaction(-100, 55, "\U0001f525")

    assert result == {"ok": True, "result": True}
    assert len(http.calls) == 1
    assert http.sleeps == []
    assert http.calls[0] == {
        "chat_id": -100,
        "message_id": 55,
        "reaction": [{"type": "emoji", "emoji": "\U0001f525"}],
    }


def test_reaction_retries_after_429(bot, http):
    http.responses = [_429(retry_after=7), FakeResponse(200, {"ok": True})]

    result = bot.set_message_reaction(1, 2)

    assert result["ok"] is True
    assert len(http.calls) == 2
    assert http.sleeps == [7]


def test_reaction_gives_up_after_three_429(bot, http):
    http.responses = [_429(), _429(), _429()]

    result = bot.set_message_reaction(1, 2)

    assert result == {"ok": False, "error": "Rate limit exceeded"}
    assert len(http.calls) == 3
    assert len(http.sleeps) == 3


def test_reaction_does_not_retry_on_http_error(bot, http):
    http.responses = [FakeResponse(500)]

    result = bot.set_message_reaction(1, 2)

    assert result["ok"] is False
    assert len(http.calls) == 1
    assert http.sleeps == []


def test_reaction_network_error_returns_not_ok(bot, http):
    http.responses = [requests.exceptions.ConnectionError("down")]

    result = bot.set_message_reaction(1, 2)

    assert result["ok"] is False
    assert "down" in result["error"]
    assert len(http.calls) == 1


def test_reaction_api_ok_false_passes_through(bot, http):
    http.responses = [FakeResponse(200, {"ok": False, "description": "bad"})]

    result = bot.set_message_reaction(1, 2)

    assert result == {"ok": False, "description": "bad"}
    assert len(http.calls) == 1


def test_send_message_escape_dict_ignores_stray_braces(bot, http):
    # str.format на таком шаблоне бросал KeyError/IndexError, сообщение не уходило вовсе
    http.responses = [FakeResponse(200, {"ok": True})]

    result = bot.send_message(1, "{} {x} {message}", escape={"message": "<b>"})

    assert result["ok"] is True
    assert http.calls[0]["text"] == "{} {x} &lt;b&gt;"


def test_send_message_escape_dict_keeps_template_markup(bot, http):
    http.responses = [FakeResponse(200, {"ok": True})]

    bot.send_message(1, "<b>{name}</b>", escape={"name": "a&b"})

    assert http.calls[0]["text"] == "<b>a&amp;b</b>"


def test_send_message_repairs_markup_on_entities_error(bot, http):
    http.responses = [
        FakeResponse(400, {"ok": False, "description": "Bad Request: can't parse entities"}),
        FakeResponse(200, {"ok": True}),
    ]

    result = bot.send_message(1, "<b>по<па</b>")

    assert result["ok"] is True
    assert len(http.calls) == 2
    assert http.calls[0]["text"] == "<b>по<па</b>"
    # второй запрос — уже починенный текст, разметка сохранена
    assert http.calls[1]["text"] == "<b>по&lt;па</b>"
    assert http.calls[1]["parse_mode"] == "HTML"


def test_send_message_falls_back_to_plain_if_repair_failed(bot, http):
    http.responses = [
        FakeResponse(400, {"ok": False, "description": "Bad Request: can't parse entities"}),
        FakeResponse(400, {"ok": False, "description": "Bad Request: can't parse entities"}),
        FakeResponse(200, {"ok": True}),
    ]

    result = bot.send_message(1, "<b>жо<па</b>")

    assert result["ok"] is True
    assert len(http.calls) == 3
    assert "parse_mode" in http.calls[0]
    assert "parse_mode" in http.calls[1]
    assert "parse_mode" not in http.calls[2]
    # plain-отправка идёт уже починенным текстом — тегов там нет, отображается как есть
    assert http.calls[2]["text"] == "<b>жо&lt;па</b>"


def test_send_message_does_not_retry_on_other_400(bot, http):
    http.responses = [
        FakeResponse(400, {"ok": False, "description": "Bad Request: chat not found"})
    ]

    result = bot.send_message(1, "text")

    assert result["ok"] is False
    assert len(http.calls) == 1
