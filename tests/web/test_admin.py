from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from flask import Flask

from src.bot.services.comments import CommentsManager
from src.bot.services.message_logging import MessageLogsManager
from src.database.models import Banword, Comment, CommentTypes, PermissionLevel
from src.shared.time_utils import get_moscow_date
from src.web import auth as web_auth
from src.web.admin import admin

AUTH = ("admin", "test_pass_123")


@pytest.fixture
def admin_app(db_manager, monkeypatch):
    monkeypatch.setattr(web_auth.config, "ADMIN_USER", AUTH[0])
    monkeypatch.setattr(web_auth.config, "ADMIN_PASS", AUTH[1])

    app = Flask("src.web", template_folder="templates")
    app.register_blueprint(admin)
    app.extensions["bot"] = SimpleNamespace(
        db=db_manager,
        comments_manager=CommentsManager(db_manager),
        logs_manager=MessageLogsManager(db_manager.db_file),
    )
    return app


@pytest.fixture
def client(admin_app):
    return admin_app.test_client()


@pytest.fixture
def db(admin_app):
    return admin_app.extensions["bot"].db


GROUP_ID = -1001234567890
USER_ID = 777


def test_requires_auth(client):
    resp = client.get("tgbot/admin/")
    assert resp.status_code == 401


def test_dashboard_empty(client):
    resp = client.get("tgbot/admin/", auth=AUTH)
    assert resp.status_code == 200
    assert "В базе ещё нет групп" in resp.data.decode("utf-8")


def test_dashboard_with_group(client, db, user_factory):
    db.add_user(user_factory(tg_group_id=GROUP_ID, tg_user_id=USER_ID))
    resp = client.get("tgbot/admin/", auth=AUTH)
    assert resp.status_code == 200
    assert str(GROUP_ID) in resp.data.decode("utf-8")


def test_users_page_and_change_permission(client, db):
    assert db.add_user(
        SimpleNamespace(
            tg_group_id=GROUP_ID,
            tg_user_id=USER_ID,
            username="vasya",
            permission=PermissionLevel.BASE,
        )
    )
    resp = client.get("tgbot/admin/users", auth=AUTH)
    assert resp.status_code == 200
    assert "@vasya" in resp.data.decode("utf-8")

    resp = client.post(
        "tgbot/admin/users/permission",
        data={"group": GROUP_ID, "user": USER_ID, "permission": PermissionLevel.MODER.value},
        auth=AUTH,
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Права обновлены" in resp.data.decode("utf-8")
    assert db.get_user(USER_ID, GROUP_ID).permission == PermissionLevel.MODER


def test_change_permission_invalid_level(client, db, user_factory):
    db.add_user(user_factory(tg_group_id=GROUP_ID, tg_user_id=USER_ID))
    resp = client.post(
        "tgbot/admin/users/permission",
        data={"group": GROUP_ID, "user": USER_ID, "permission": 99},
        auth=AUTH,
        follow_redirects=True,
    )
    assert "Неизвестный уровень прав" in resp.data.decode("utf-8")
    assert db.get_user(USER_ID, GROUP_ID).permission == PermissionLevel.BASE


def test_delete_user(client, db, user_factory):
    db.add_user(user_factory(tg_group_id=GROUP_ID, tg_user_id=USER_ID))
    resp = client.post(
        "tgbot/admin/users/delete",
        data={"group": GROUP_ID, "user": USER_ID},
        auth=AUTH,
        follow_redirects=True,
    )
    assert "Пользователь удалён из группы" in resp.data.decode("utf-8")
    assert db.get_user(USER_ID, GROUP_ID) is None


def test_comments_add_and_delete(client, db):
    resp = client.get("tgbot/admin/comments", auth=AUTH)
    assert resp.status_code == 200

    resp = client.post(
        "tgbot/admin/comments/add",
        data={"group": GROUP_ID, "type": "text", "text": "Привет {{name}}"},
        auth=AUTH,
        follow_redirects=True,
    )
    assert "Комментарий добавлен" in resp.data.decode("utf-8")
    comments = db.get_comments_with_ids(GROUP_ID)
    assert len(comments) == 1
    assert comments[0]["comment_text"] == "Привет {{name}}"

    resp = client.post(
        "tgbot/admin/comments/delete",
        data={"group": GROUP_ID, "comment_id": comments[0]["id"]},
        auth=AUTH,
        follow_redirects=True,
    )
    assert "Комментарий удалён" in resp.data.decode("utf-8")
    assert db.get_comments_with_ids(GROUP_ID) == []


def test_comments_duplicate_rejected(client, db):
    for _ in range(2):
        resp = client.post(
            "tgbot/admin/comments/add",
            data={"group": GROUP_ID, "type": "text", "text": "дубль"},
            auth=AUTH,
            follow_redirects=True,
        )
    assert "Такой комментарий уже существует" in resp.data.decode("utf-8")
    assert len(db.get_comments_with_ids(GROUP_ID)) == 1


def test_comments_add_empty_text_rejected(client, db):
    resp = client.post(
        "tgbot/admin/comments/add",
        data={"group": GROUP_ID, "type": "text", "text": "   "},
        auth=AUTH,
        follow_redirects=True,
    )
    assert "Укажите группу, тип и текст" in resp.data.decode("utf-8")
    assert db.get_comments_with_ids(GROUP_ID) == []


def test_comments_scheduled_requires_future_date(client, db):
    today = date.fromisoformat(get_moscow_date())
    past = (today - timedelta(days=1)).isoformat()
    resp = client.post(
        "tgbot/admin/comments/add",
        data={"group": GROUP_ID, "type": "scheduled", "text": "завтрашний", "scheduled_date": past},
        auth=AUTH,
        follow_redirects=True,
    )
    assert "не раньше сегодняшней" in resp.data.decode("utf-8")
    assert db.get_comments_with_ids(GROUP_ID) == []


def test_comments_scheduled_ok(client, db):
    future = (date.fromisoformat(get_moscow_date()) + timedelta(days=3)).isoformat()
    resp = client.post(
        "tgbot/admin/comments/add",
        data={
            "group": GROUP_ID,
            "type": "scheduled",
            "text": "запланирован",
            "scheduled_date": future,
        },
        auth=AUTH,
        follow_redirects=True,
    )
    assert "Комментарий добавлен" in resp.data.decode("utf-8")
    comments = db.get_comments_with_ids(GROUP_ID)
    assert comments[0]["scheduled_date"] == future
    assert future in resp.data.decode("utf-8")


def test_banwords_add_invalid_regex(client, db):
    resp = client.post(
        "tgbot/admin/banwords/add",
        data={"group": GROUP_ID, "pattern": "([несбалансирована", "reply": "стоп"},
        auth=AUTH,
        follow_redirects=True,
    )
    assert "Паттерн не компилируется" in resp.data.decode("utf-8")
    assert db.get_banwords_list(GROUP_ID) == []


def test_banwords_add_and_delete(client, db):
    resp = client.get("tgbot/admin/banwords", auth=AUTH)
    assert resp.status_code == 200

    resp = client.post(
        "tgbot/admin/banwords/add",
        data={"group": GROUP_ID, "pattern": "казино", "reply": "Реклама запрещена"},
        auth=AUTH,
        follow_redirects=True,
    )
    assert "Банворд добавлен" in resp.data.decode("utf-8")
    banwords = db.get_banwords_list(GROUP_ID)
    assert len(banwords) == 1
    assert banwords[0].pattern == "казино"

    resp = client.post(
        "tgbot/admin/banwords/delete",
        data={"group": GROUP_ID, "pattern": "казино"},
        auth=AUTH,
        follow_redirects=True,
    )
    assert "Банворд удалён" in resp.data.decode("utf-8")
    assert db.get_banwords_list(GROUP_ID) == []


def test_wrong_password_returns_403(client):
    resp = client.get("tgbot/admin/", auth=("admin", "wrong"))
    assert resp.status_code == 403


def test_foreign_origin_post_rejected(client, db):
    resp = client.post(
        "tgbot/admin/banwords/add",
        data={"group": GROUP_ID, "pattern": "казино", "reply": "нет"},
        headers={"Origin": "https://evil.example"},
        auth=AUTH,
    )
    assert resp.status_code == 403
    assert db.get_banwords_list(GROUP_ID) == []


def test_same_origin_post_allowed(client, db):
    resp = client.post(
        "tgbot/admin/banwords/add",
        data={"group": GROUP_ID, "pattern": "казино", "reply": "нет"},
        headers={"Origin": "http://localhost"},
        auth=AUTH,
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Банворд добавлен" in resp.data.decode("utf-8")
    assert len(db.get_banwords_list(GROUP_ID)) == 1


def test_comment_from_other_group_not_deleted(client, db):
    db.add_comment(Comment(GROUP_ID, CommentTypes.TEXT, "чужой"))
    comment_id = db.get_comments_with_ids(GROUP_ID)[0]["id"]

    resp = client.post(
        "tgbot/admin/comments/delete",
        data={"group": GROUP_ID + 1, "comment_id": comment_id},
        auth=AUTH,
        follow_redirects=True,
    )
    assert "Комментарий не найден" in resp.data.decode("utf-8")
    assert len(db.get_comments_with_ids(GROUP_ID)) == 1


def test_banword_delete_invalidates_cache(client, db):
    db.add_banword(GROUP_ID, "казино", "нет")
    db.set_banwords_cache(GROUP_ID, [Banword(GROUP_ID, "казино", "нет")], ttl=300)
    assert db.get_banwords_cache(GROUP_ID) is not None

    resp = client.post(
        "tgbot/admin/banwords/delete",
        data={"group": GROUP_ID, "pattern": "казино"},
        auth=AUTH,
        follow_redirects=True,
    )
    assert "Банворд удалён" in resp.data.decode("utf-8")
    assert db.get_banwords_cache(GROUP_ID) is None


def test_logs_page_empty(client):
    resp = client.get("tgbot/admin/logs", auth=AUTH)
    assert resp.status_code == 200
    assert "Пока пусто" in resp.data.decode("utf-8")


def test_logs_page_shows_entries(client, admin_app):
    admin_app.extensions["bot"].logs_manager.add_message_log(11, GROUP_ID, 22, "текст лога")
    resp = client.get("tgbot/admin/logs", auth=AUTH)
    body = resp.data.decode("utf-8")
    assert resp.status_code == 200
    assert "текст лога" in body
    assert "11" in body


def test_api_stats(client, db, user_factory):
    db.add_user(user_factory(tg_group_id=GROUP_ID, tg_user_id=USER_ID))
    resp = client.get("tgbot/admin/api/stats", auth=AUTH)
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["totals"]["groups"] == 1
    assert payload["totals"]["users"] == 1
    assert payload["groups"][0]["group_id"] == GROUP_ID
    assert len(payload["activity"]) == 24


def test_api_logs(client, admin_app):
    admin_app.extensions["bot"].logs_manager.add_message_log(5, GROUP_ID, 6, "привет")
    resp = client.get("tgbot/admin/api/logs", auth=AUTH)
    assert resp.status_code == 200
    payload = resp.get_json()
    assert len(payload["rows"]) == 1
    assert payload["rows"][0]["text"] == "привет"


def test_export_json(client, db, user_factory, admin_app):
    db.add_user(user_factory(tg_group_id=GROUP_ID, tg_user_id=USER_ID, username="vasya"))
    db.add_comment(Comment(GROUP_ID, CommentTypes.TEXT, "экспорт"))
    db.add_banword(GROUP_ID, "казино", "нет")
    admin_app.extensions["bot"].logs_manager.add_message_log(1, GROUP_ID, 2, "лог")

    resp = client.get("tgbot/admin/export.json", auth=AUTH)
    assert resp.status_code == 200
    assert "attachment" in resp.headers["Content-Disposition"]
    payload = resp.get_json()
    assert payload["groups"] == [GROUP_ID]
    assert payload["users"][str(GROUP_ID)][0]["username"] == "vasya"
    assert payload["comments"][str(GROUP_ID)]["text"][0]["comment_text"] == "экспорт"
    assert payload["banwords"][str(GROUP_ID)][0]["pattern"] == "казино"
