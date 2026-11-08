from dataclasses import asdict
from typing import Any, Dict

from src.shared.time_utils import get_moscow_datetime_str


def _comments_payload(db, group_id: int) -> Dict[str, Any]:
    data = db.get_comments_list(group_id)
    return {
        "text": [asdict(comment) for comment in data.get("text", [])],
        "photo": [asdict(comment) for comment in data.get("photo", [])],
        "scheduled": {
            day: [asdict(comment) for comment in items]
            for day, items in (data.get("scheduled") or {}).items()
        },
    }


def get_all_data(bot) -> Dict[str, Any]:
    """Снимок всей базы для выгрузки из админки.

    Работает через уже проверенные методы репозитория и сервисов,
    чтобы не дублировать SQL.
    """
    db = bot.db
    logs_manager = getattr(bot, "logs_manager", None)
    groups = db.get_groups()

    users = {
        group_id: [asdict(user) for user in db.get_users_in_group(group_id)] for group_id in groups
    }
    comments = {group_id: _comments_payload(db, group_id) for group_id in groups}
    banwords = {
        group_id: [asdict(banword) for banword in db.get_banwords_list(group_id)]
        for group_id in groups
    }

    return {
        "exported_at": get_moscow_datetime_str(),
        "groups": groups,
        "users": users,
        "comments": comments,
        "banwords": banwords,
        "logs": logs_manager.get_logged_messages() if logs_manager else {},
    }
