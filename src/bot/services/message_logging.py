import sqlite3
from typing import Optional, Dict, Any
from contextlib import closing
from src.shared.time_utils import get_moscow_now
import logging

logger = logging.getLogger(__name__)


class MessageLogsManager:
    def __init__(self, db_file: str):
        self.db_file = db_file

    def _conn(self):
        conn = sqlite3.connect(self.db_file, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def add_message_log(self, bot_msg_id: int, chat_id: int, original_msg_id: int, text: str) -> None:
        current_time = get_moscow_now()
        try:
            with closing(self._conn()) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO message_logs (bot_message_id, chat_id, original_message_id, text, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (bot_msg_id, chat_id, original_msg_id, text, current_time),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Ошибка добавления лога: {e}")

    def get_message_info(self, bot_msg_id: int) -> Optional[Dict[str, Any]]:
        with closing(self._conn()) as conn:
            row = conn.execute("SELECT chat_id, original_message_id, text FROM message_logs WHERE bot_message_id=?", (bot_msg_id,)).fetchone()
            return {"chat_id": row[0], "message_id": row[1], "text": row[2]} if row else None

    def get_bot_message_info(self, message_id: int) -> Optional[Dict[str, Any]]:
        with closing(self._conn()) as conn:
            row = conn.execute(
                "SELECT bot_message_id, chat_id, text, timestamp FROM message_logs WHERE original_message_id=?", (message_id,)
            ).fetchone()
            return {str(row["bot_message_id"]): dict(row)} if row else None

    def cleanup_old_logs(self) -> int:
        current_time = get_moscow_now()
        cutoff = current_time - (24 * 60 * 60)
        try:
            with closing(self._conn()) as conn:
                cursor = conn.execute("DELETE FROM message_logs WHERE timestamp < ?", (cutoff,))
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Ошибка очистки логов: {e}")
            return 0

    def get_logged_messages(self) -> Dict[str, Dict[str, Any]]:
        with closing(self._conn()) as conn:
            rows = conn.execute("SELECT bot_message_id, chat_id, text, timestamp FROM message_logs").fetchall()
            return {str(row["bot_message_id"]): dict(row) for row in rows}
