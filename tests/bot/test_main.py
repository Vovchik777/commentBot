import base64
import os
import sqlite3
import sys

import pytest


def _basic_auth(user, password):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture(scope="module")
def main_module(tmp_path_factory):
    db_dir = tmp_path_factory.mktemp("maindb")
    overrides = {
        "BOT_TOKEN": "123456:TESTTOKEN",
        "LOGGER_CHAT_ID": "0",
        "WEBHOOK_SECRET": "test-webhook-secret-1234",
        "ADMIN_USER": "admin",
        "ADMIN_PASS": "test-admin-pass",
        "DB_FILE": str(db_dir / "main.db"),
    }
    saved = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)

    sys.modules.pop("src.main", None)
    sys.modules.pop("src.config", None)
    import src.config  # noqa: F401
    import src.main

    src.main.application.config["TESTING"] = True

    @src.main.application.route("/_test_admin")
    @src.main.require_admin
    def _test_admin():
        return "ok"

    yield src.main

    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture
def client(main_module):
    conn = sqlite3.connect(main_module.config.DB_FILE)
    try:
        conn.execute("DELETE FROM admin_msg_rate_limits")
        conn.commit()
    finally:
        conn.close()
    return main_module.application.test_client()


@pytest.fixture
def sent(main_module, monkeypatch):
    calls = []

    def fake_send(
        chat_id, text, reply_to_message_id=None, reply_markup=None, parse_mode="HTML", escape=False
    ):
        calls.append({"chat_id": chat_id, "text": text, "escape": escape})
        return {"ok": True, "result": {"message_id": 1}}

    monkeypatch.setattr(main_module.bot, "send_message", fake_send)
    return calls


def test_require_admin_without_credentials(client):
    assert client.get("/_test_admin").status_code == 401


def test_require_admin_wrong_password(client):
    response = client.get("/_test_admin", headers=_basic_auth("admin", "wrong"))
    assert response.status_code == 403


def test_require_admin_ok(client):
    response = client.get("/_test_admin", headers=_basic_auth("admin", "test-admin-pass"))
    assert response.status_code == 200


def test_webhook_rejects_missing_secret(client, main_module, monkeypatch):
    monkeypatch.setattr(main_module.bot, "process_update", lambda data: None)
    assert client.post("/tgbot/webhook", json={}).status_code == 401


def test_webhook_rejects_wrong_secret(client, main_module, monkeypatch):
    monkeypatch.setattr(main_module.bot, "process_update", lambda data: None)
    response = client.post(
        "/tgbot/webhook", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"}
    )
    assert response.status_code == 401


def test_webhook_accepts_valid_secret(client, main_module, monkeypatch):
    monkeypatch.setattr(main_module.bot, "process_update", lambda data: None)
    response = client.post(
        "/tgbot/webhook",
        json={},
        headers={"X-Telegram-Bot-Api-Secret-Token": main_module.config.SECRET_TOKEN},
    )
    assert response.status_code == 200


def test_admin_msg_empty_message(client, sent):
    response = client.post("/tgbot/admin_msg", json={"message": "   "})
    assert response.status_code == 400
    assert sent == []


def test_admin_msg_honeypot_is_silently_dropped(client, sent):
    response = client.post("/tgbot/admin_msg", json={"message": "hi", "website": "spam"})
    assert response.status_code == 200
    assert sent == []


def test_admin_msg_success_passes_escaping(client, sent, main_module):
    response = client.post("/tgbot/admin_msg", json={"message": "hello <b>world</b>"})
    assert response.status_code == 200
    assert len(sent) == 1
    assert sent[0]["chat_id"] == main_module.config.LOGGER_CHAT_ID
    assert sent[0]["escape"] == {"message": "hello <b>world</b>"}
    assert sent[0]["text"].startswith(main_module.config.ADMIN_MSG_HEADER)
    assert sent[0]["text"].endswith("{message}")


def test_admin_msg_too_long(main_module, client, monkeypatch):
    monkeypatch.setattr(
        main_module.bot, "send_message", lambda *a, **k: {"ok": False, "error": "too_long"}
    )
    response = client.post("/tgbot/admin_msg", json={"message": "x"})
    assert response.status_code == 400


def test_admin_msg_rate_limited(client, sent, main_module):
    for _ in range(main_module.config.ADMIN_MSG_RATE_LIMIT):
        assert client.post("/tgbot/admin_msg", json={"message": "hi"}).status_code == 200
    response = client.post("/tgbot/admin_msg", json={"message": "hi"})
    assert response.status_code == 429


def test_send_message_escape_dict(main_module, monkeypatch):
    calls = []
    monkeypatch.setattr(
        main_module.bot,
        "_send_single_message",
        lambda chat_id, text, *a, **k: (calls.append(text), {"ok": True})[1],
    )
    main_module.bot.send_message(1, "<b>H</b>\n{message}", escape={"message": "<script>"})
    assert calls == ["<b>H</b>\n&lt;script&gt;"]


def test_send_message_escape_too_long(main_module, monkeypatch):
    monkeypatch.setattr(main_module.bot, "_send_single_message", lambda *a, **k: {"ok": True})
    result = main_module.bot.send_message(1, "{message}", escape={"message": "x" * 5000})
    assert result == {"ok": False, "error": "too_long"}
