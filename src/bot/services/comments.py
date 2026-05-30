import sqlite3
import random
import re
from src.shared.logger import get_db_logger
from typing import Optional, Dict, Any
from faker import Faker
import logging
from contextlib import closing

logger = get_db_logger()


class CommentsManager:
    def __init__(self, db_file: str):
        self.db_file = db_file
        self.faker = Faker("ru_RU")
        self.faker_replace = {
            "name": lambda: self.faker.name(),
            "address": lambda: self.faker.address(),
            "phone_number": lambda: self.faker.phone_number(),
            "company": lambda: self.faker.company(),
        }

    def _conn(self):
        return sqlite3.connect(self.db_file, timeout=10)

    def init_group_comments(self, group_id: int) -> None:
        logger.info(f"Группа {group_id} готова к работе с комментариями (SQLite)")

    def add_comment(self, comment_type: str, text: str, group_id: int) -> bool:
        try:
            with closing(self._conn()) as conn:
                conn.execute("INSERT OR IGNORE INTO comments (group_id, comment_type, comment_text) VALUES (?, ?, ?)", (group_id, comment_type, text))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка добавления комментария: {e}")
            return False

    def add_scheduled_comment(self, text: str, group_id: int, date: str) -> bool:
        try:
            with closing(self._conn()) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO comments (group_id, comment_type, comment_text, scheduled_date) VALUES (?, 'scheduled', ?, ?)",
                    (group_id, text, date),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка добавления запланированного: {e}")
            return False

    def delete_comment(self, group_id: int, comment_type: str, index: int) -> Optional[str]:
        with closing(self._conn()) as conn:
            if comment_type == "scheduled":
                cursor = conn.execute(
                    "SELECT id, comment_text FROM comments WHERE group_id=? AND comment_type='scheduled' ORDER BY scheduled_date, id LIMIT 1 OFFSET ?",
                    (group_id, index - 1),
                )
            else:
                cursor = conn.execute(
                    "SELECT id, comment_text FROM comments WHERE group_id=? AND comment_type=? LIMIT 1 OFFSET ?", (group_id, comment_type, index - 1)
                )
            row = cursor.fetchone()
            if row:
                conn.execute("DELETE FROM comments WHERE id=?", (row[0],))
                conn.commit()
                return row[1]
            return None

    def get_random_comment(self, group_id: int, comment_type: str) -> Optional[str]:
        with closing(self._conn()) as conn:
            row = conn.execute(
                "SELECT comment_text FROM comments WHERE group_id=? AND comment_type=? ORDER BY RANDOM() LIMIT 1", (group_id, comment_type)
            ).fetchone()
            return row[0] if row else None

    def get_scheduled_for_today(self, group_id: int, today_str: str) -> list[str]:
        with closing(self._conn()) as conn:
            rows = conn.execute(
                "SELECT comment_text FROM comments WHERE group_id=? AND comment_type='scheduled' AND scheduled_date=?", (group_id, today_str)
            ).fetchall()
            return [r[0] for r in rows]

    def get_comments_list(self, group_id: int) -> Dict[str, Any]:
        result = {"text": [], "photo": [], "scheduled": {}}
        with closing(self._conn()) as conn:
            for row in conn.execute("SELECT comment_type, comment_text, scheduled_date FROM comments WHERE group_id=?", (group_id,)):
                if row[0] == "scheduled":
                    result["scheduled"].setdefault(row[2], []).append(row[1])
                else:
                    result[row[0]].append(row[1])
        return result

    def parse_comment_template(self, comment: str) -> str:
        templates = re.findall(r"{{\w+}}", comment)
        for template in templates:
            key = template.strip("{}")
            if key in self.faker_replace:
                comment = comment.replace(template, self.faker_replace[key]())
        return comment
