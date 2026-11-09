import json
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, Response, current_app, redirect, render_template, request, url_for

from src.bot.services.snapshot import get_all_data
from src.database.models import Comment, CommentTypes, PermissionLevel
from src.shared.logger import get_bot_logger
from src.shared.time_utils import (
    MOSCOW_TZ,
    get_moscow_date,
    get_moscow_datetime_str,
    get_moscow_now,
)
from src.web.auth import _forbidden, _unauthorized, get_config, is_admin_request, is_safe_origin

logger = get_bot_logger()

admin = Blueprint("admin", __name__, url_prefix="/tgbot/admin")

MAX_LOG_ROWS = 200
ACTIVITY_HOURS = 24


@admin.before_request
def check_admin():
    if not is_admin_request():
        if request.authorization:
            return _forbidden()
        return _unauthorized()
    if request.method == "POST" and not is_safe_origin():
        logger.warning(
            f"Админка: отклонён POST с чужого источника ({request.headers.get('Origin')})"
        )
        return _forbidden()


@admin.after_request
def security_headers(response):
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@admin.context_processor
def inject_globals():
    return {
        "config": get_config(),
        "permissions": [(level.value, level.to_string()) for level in PermissionLevel],
        "today": get_moscow_date(),
    }


def _bot():
    return current_app.extensions["bot"]


def _redirect_msg(endpoint: str, text: str, **params):
    return redirect(url_for(endpoint, msg=text, **params))


def _parse_int(raw: Any) -> Optional[int]:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _selected_group(groups: List[int]) -> Optional[int]:
    requested = request.args.get("group", type=int)
    if requested is not None:
        return requested
    return groups[0] if groups else None


def _group_title(bot: Any, group_id: int) -> str:
    """Название группы из getChat; пустая строка, если получить не удалось."""
    get_info = getattr(bot, "get_chat_info", None)
    if not callable(get_info):
        return ""
    info = get_info(group_id)
    if isinstance(info, dict):
        return str(info.get("title") or "").strip()
    return str(info or "").strip()


def _group_titles(bot: Any, group_ids: List[int]) -> Dict[int, str]:
    return {group_id: _group_title(bot, group_id) for group_id in group_ids}


CHAT_LABEL_TTL = 300
_chat_labels_cache: Dict[int, tuple] = {}


def _chat_label(bot: Any, chat_id: Any) -> str:
    """Название чата (группа/канал) или имя пользователя; кэш на 5 минут."""
    if chat_id is None:
        return ""
    key = (
        int(chat_id)
        if isinstance(chat_id, (int, str)) and str(chat_id).lstrip("-").isdecimal()
        else 0
    )
    if key:
        cached = _chat_labels_cache.get(key)
        if cached and cached[0] > time.time():
            return cached[1]

    get_info = getattr(bot, "get_chat_info", None)
    if not callable(get_info):
        return ""
    info = get_info(key or chat_id)
    if isinstance(info, dict):
        label = (
            info.get("title")
            or " ".join(filter(None, [info.get("first_name"), info.get("last_name")]))
            or info.get("username")
            or ""
        )
        label = str(label).strip()
    else:
        label = str(info or "").strip()

    if key:
        _chat_labels_cache[key] = (time.time() + CHAT_LABEL_TTL, label)
    return label


def _comments_payload(group_id: int) -> Dict[str, Any]:
    data = _bot().db.get_comments_list(group_id)
    scheduled = data.get("scheduled") or {}
    comment_total = len(data.get("text", [])) + len(data.get("photo", []))
    comment_total += sum(len(items) for items in scheduled.values())
    return {
        "text": data.get("text", []),
        "photo": data.get("photo", []),
        "scheduled": scheduled,
        "total": comment_total,
    }


def _collect_stats() -> Dict[str, Any]:
    bot = _bot()
    db = bot.db
    logs = bot.logs_manager.get_logged_messages() if getattr(bot, "logs_manager", None) else {}

    groups: List[Dict[str, Any]] = []
    for group_id in db.get_groups():
        title = _group_title(bot, group_id)
        users = db.get_users_in_group(group_id)
        comments = _comments_payload(group_id)
        banwords = db.get_banwords_list(group_id)
        all_comments = (
            comments["text"]
            + comments["photo"]
            + [comment for items in comments["scheduled"].values() for comment in items]
        )
        groups.append(
            {
                "title": title,
                "group_id": group_id,
                "users": len(users),
                "text": len(comments["text"]),
                "photo": len(comments["photo"]),
                "scheduled": sum(len(items) for items in comments["scheduled"].values()),
                "banwords": len(banwords),
                "use_count": sum(comment.use_count for comment in all_comments),
            }
        )

    totals = {
        "groups": len(groups),
        "users": sum(item["users"] for item in groups),
        "comments": sum(item["text"] + item["photo"] + item["scheduled"] for item in groups),
        "banwords": sum(item["banwords"] for item in groups),
        "use_count": sum(item["use_count"] for item in groups),
        "logs": len(logs),
    }

    return {
        "generated_at": time.time(),
        "generated_at_str": get_moscow_datetime_str("%H:%M:%S"),
        "groups": groups,
        "totals": totals,
        "activity": _activity_buckets(logs),
    }


def _activity_buckets(logs: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    now = get_moscow_now()
    buckets = [0] * ACTIVITY_HOURS
    for entry in logs.values():
        timestamp = entry.get("timestamp")
        if not timestamp:
            continue
        age = now - float(timestamp)
        if 0 <= age < ACTIVITY_HOURS * 3600:
            index = ACTIVITY_HOURS - 1 - int(age // 3600)
            buckets[index] += 1

    result = []
    for index, count in enumerate(buckets):
        hours_ago = ACTIVITY_HOURS - 1 - index
        moment = datetime.fromtimestamp(now - hours_ago * 3600, MOSCOW_TZ)
        result.append({"label": moment.strftime("%H:00"), "count": count})
    return result


def _logs_rows(limit: int = MAX_LOG_ROWS) -> List[Dict[str, Any]]:
    bot = _bot()
    logs_manager = getattr(bot, "logs_manager", None)
    if logs_manager is None:
        return []

    rows = list(logs_manager.get_logged_messages().values())
    rows.sort(key=lambda row: row.get("timestamp") or 0, reverse=True)
    result = []
    for row in rows[:limit]:
        timestamp = row.get("timestamp") or 0
        chat_id = row.get("chat_id")
        result.append(
            {
                "bot_message_id": row.get("bot_message_id"),
                "chat_id": chat_id,
                "chat_title": _chat_label(bot, chat_id),
                "text": row.get("text") or "",
                "timestamp": timestamp,
                "time": datetime.fromtimestamp(timestamp, MOSCOW_TZ).strftime("%d.%m.%Y %H:%M:%S")
                if timestamp
                else "—",
            }
        )
    return result


# --- СТРАНИЦЫ ---


@admin.get("/")
def dashboard():
    stats = _collect_stats()
    return render_template(
        "admin_dashboard.html",
        stats=stats["groups"],
        totals=stats["totals"],
        activity=stats["activity"],
        msg=request.args.get("msg", ""),
    )


@admin.get("/users")
def users_page():
    bot = _bot()
    db = bot.db
    groups = db.get_groups()
    titles = _group_titles(bot, groups)
    data = [(group_id, titles[group_id], db.get_users_in_group(group_id)) for group_id in groups]
    return render_template("admin_users.html", data=data, msg=request.args.get("msg", ""))


@admin.get("/comments")
def comments_page():
    bot = _bot()
    db = bot.db
    groups = db.get_groups()
    group_id = _selected_group(groups)
    text_comments: List[Comment] = []
    photo_comments: List[Comment] = []
    scheduled: Dict[str, List[Comment]] = {}
    if group_id is not None:
        payload = _comments_payload(group_id)
        text_comments = payload["text"]
        photo_comments = payload["photo"]
        scheduled = payload["scheduled"]

    return render_template(
        "admin_comments.html",
        groups=groups,
        group_titles=_group_titles(bot, groups),
        group_id=group_id,
        comment_types=[comment_type.value for comment_type in CommentTypes],
        text_comments=text_comments,
        photo_comments=photo_comments,
        scheduled=scheduled,
        msg=request.args.get("msg", ""),
    )


@admin.get("/banwords")
def banwords_page():
    bot = _bot()
    db = bot.db
    groups = db.get_groups()
    group_id = _selected_group(groups)
    banwords = db.get_banwords_list(group_id) if group_id is not None else []
    return render_template(
        "admin_banwords.html",
        groups=groups,
        group_titles=_group_titles(bot, groups),
        group_id=group_id,
        banwords=banwords,
        msg=request.args.get("msg", ""),
    )


@admin.get("/logs")
def logs_page():
    return render_template(
        "admin_logs.html",
        rows=_logs_rows(),
        max_rows=MAX_LOG_ROWS,
        msg=request.args.get("msg", ""),
    )


# --- ДЕЙСТВИЯ ---


@admin.post("/users/permission")
def change_permission():
    group_id = _parse_int(request.form.get("group"))
    user_id = _parse_int(request.form.get("user"))
    permission_value = _parse_int(request.form.get("permission"))
    if group_id is None or user_id is None or permission_value is None:
        return _redirect_msg("admin.users_page", "Неизвестный уровень прав")

    try:
        permission = PermissionLevel(permission_value)
    except ValueError:
        return _redirect_msg("admin.users_page", "Неизвестный уровень прав")

    db = _bot().db
    user = db.get_user(user_id, group_id)
    if user is None:
        return _redirect_msg("admin.users_page", "Пользователь не найден")
    if not db.update_user_permission(user, permission):
        return _redirect_msg("admin.users_page", "Не удалось обновить права")

    logger.info(f"Админка: права {user_id} в группе {group_id} → {permission.name}")
    return _redirect_msg("admin.users_page", "Права обновлены")


@admin.post("/users/delete")
def delete_user():
    group_id = _parse_int(request.form.get("group"))
    user_id = _parse_int(request.form.get("user"))
    if group_id is None or user_id is None:
        return _redirect_msg("admin.users_page", "Пользователь не найден")

    db = _bot().db
    user = db.get_user(user_id, group_id)
    if user is None or not db.delete_user(user):
        return _redirect_msg("admin.users_page", "Пользователь не найден")

    logger.info(f"Админка: пользователь {user_id} удалён из группы {group_id}")
    return _redirect_msg("admin.users_page", "Пользователь удалён из группы")


@admin.post("/comments/add")
def add_comment():
    group_id = _parse_int(request.form.get("group"))
    comment_type = CommentTypes.from_str(request.form.get("type", ""))
    text = (request.form.get("text") or "").strip()
    if group_id is None or comment_type is None or not text:
        return _redirect_msg(
            "admin.comments_page", "Укажите группу, тип и текст", group=group_id or ""
        )

    scheduled_date = None
    if comment_type == CommentTypes.SCHEDULED:
        scheduled_date = Comment.parse_scheduled_date(
            (request.form.get("scheduled_date") or "").strip()
        )
        if scheduled_date is None:
            return _redirect_msg(
                "admin.comments_page",
                "Дата должна быть не раньше сегодняшней",
                group=group_id,
            )

    comment = Comment(
        group_id=group_id,
        comment_type=comment_type,
        comment_text=text,
        scheduled_date=scheduled_date,
    )
    if not _bot().db.add_comment(comment):
        return _redirect_msg(
            "admin.comments_page", "Такой комментарий уже существует", group=group_id
        )

    logger.info(f"Админка: добавлен комментарий {comment_type.value} в группу {group_id}")
    return _redirect_msg("admin.comments_page", "Комментарий добавлен", group=group_id)


@admin.post("/comments/delete")
def delete_comment():
    group_id = _parse_int(request.form.get("group"))
    comment_id = _parse_int(request.form.get("comment_id"))
    if group_id is None or comment_id is None:
        return _redirect_msg("admin.comments_page", "Комментарий не найден", group=group_id or "")

    if not _bot().db.delete_comment_by_id(comment_id, group_id):
        return _redirect_msg("admin.comments_page", "Комментарий не найден", group=group_id)

    logger.info(f"Админка: удалён комментарий #{comment_id} из группы {group_id}")
    return _redirect_msg("admin.comments_page", "Комментарий удалён", group=group_id)


@admin.post("/banwords/add")
def add_banword():
    group_id = _parse_int(request.form.get("group"))
    pattern = (request.form.get("pattern") or "").strip()
    reply = (request.form.get("reply") or "").strip()
    if group_id is None or not pattern or not reply:
        return _redirect_msg(
            "admin.banwords_page", "Заполните паттерн и ответ", group=group_id or ""
        )

    try:
        re.compile(pattern)
    except re.error:
        return _redirect_msg("admin.banwords_page", "Паттерн не компилируется", group=group_id)

    if not _add_banword(group_id, pattern, reply):
        return _redirect_msg("admin.banwords_page", "Такой банворд уже существует", group=group_id)

    logger.info(f"Админка: добавлен банворд в группу {group_id}")
    return _redirect_msg("admin.banwords_page", "Банворд добавлен", group=group_id)


@admin.post("/banwords/delete")
def delete_banword():
    group_id = _parse_int(request.form.get("group"))
    pattern = (request.form.get("pattern") or "").strip()
    if group_id is None or not pattern:
        return _redirect_msg("admin.banwords_page", "Банворд не найден", group=group_id or "")

    if not _delete_banword(group_id, pattern):
        return _redirect_msg("admin.banwords_page", "Банворд не найден", group=group_id)

    logger.info(f"Админка: удалён банворд из группы {group_id}")
    return _redirect_msg("admin.banwords_page", "Банворд удалён", group=group_id)


def _add_banword(group_id: int, pattern: str, reply: str) -> bool:
    bot = _bot()
    manager = getattr(bot, "comments_manager", None)
    if manager is not None:
        return manager.add_banword(group_id, pattern, reply)

    added = bot.db.add_banword(group_id, pattern, reply)
    if added:
        bot.db.invalidate_banwords_cache(group_id)
    return added


def _delete_banword(group_id: int, pattern: str) -> bool:
    bot = _bot()
    removed = bot.db.delete_banword(group_id, pattern)
    if removed:
        manager = getattr(bot, "comments_manager", None)
        if manager is not None:
            manager.invalidate_banwords(group_id)
        else:
            bot.db.invalidate_banwords_cache(group_id)
    return removed


# --- API ДЛЯ ЖИВОГО ОБНОВЛЕНИЯ ---


@admin.get("/api/stats")
def api_stats():
    response = Response(
        json.dumps(_collect_stats(), ensure_ascii=False), mimetype="application/json"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@admin.get("/api/logs")
def api_logs():
    payload = {"generated_at_str": get_moscow_datetime_str("%H:%M:%S"), "rows": _logs_rows()}
    response = Response(json.dumps(payload, ensure_ascii=False), mimetype="application/json")
    response.headers["Cache-Control"] = "no-store"
    return response


@admin.get("/export.json")
def export_json():
    payload = json.dumps(get_all_data(_bot()), ensure_ascii=False, indent=2, default=str)
    return Response(
        payload,
        mimetype="application/json",
        headers={"Content-Disposition": 'attachment; filename="commentbot-export.json"'},
    )
