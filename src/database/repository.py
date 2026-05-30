import sqlite3
import time
from src.shared.logger import get_db_logger
from typing import Optional, List
from .models import User, PermissionLevel
from contextlib import closing

logger = get_db_logger()


class DataBaseManager:
    def __init__(self, db_file: str):
        self.db_file = db_file
        self._init_db()
        logger.info(f"DatabaseManager инициализирован для файла: {db_file}")

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                tg_user_id INTEGER UNIQUE
            );
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_group_id INTEGER UNIQUE
            );
            CREATE TABLE IF NOT EXISTS users_groups(
                user_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                permission INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, group_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (group_id) REFERENCES groups(id)
            );
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                comment_type TEXT NOT NULL,
                comment_text TEXT NOT NULL,
                scheduled_date TEXT,
                use_count INTEGER DEFAULT 0,
                UNIQUE(group_id, comment_type, comment_text)
            );
            CREATE TABLE IF NOT EXISTS message_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_message_id INTEGER UNIQUE,
                chat_id INTEGER NOT NULL,
                original_message_id INTEGER NOT NULL,
                text TEXT,
                timestamp REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS processed_albums (
                media_group_id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL
            );
            """)
            conn.commit()

    def create_group_table(self, tg_group_id: int) -> None:
        with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
            conn.execute("INSERT OR IGNORE INTO groups (tg_group_id) VALUES (?)", (tg_group_id,))
            conn.commit()

    def get_user(self, tg_user_id: int, tg_group_id: int) -> Optional[User]:
        with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            result = conn.execute(
                """
                SELECT u.username, ug.permission 
                FROM users AS u
                JOIN users_groups AS ug ON u.id = ug.user_id
                JOIN groups AS g ON ug.group_id = g.id
                WHERE u.tg_user_id = ? AND g.tg_group_id = ?
            """,
                (tg_user_id, tg_group_id),
            ).fetchone()
            return User(tg_user_id=tg_user_id, username=result[0], permission=PermissionLevel(result[1]), tg_group_id=tg_group_id) if result else None

    def add_user(self, user: User) -> bool:
        try:
            with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
                conn.row_factory = sqlite3.Row
                self.create_group_table(user.tg_group_id)
                cursor = conn.cursor()

                cursor.execute(
                    "INSERT INTO users (username, tg_user_id) VALUES (?,?) ON CONFLICT(tg_user_id) DO UPDATE SET username = excluded.username RETURNING id",
                    (user.username, user.tg_user_id),
                )
                user_result = cursor.fetchone()
                if not user_result:
                    cursor.execute("SELECT id FROM users WHERE tg_user_id = ?", (user.tg_user_id,))
                    user_result = cursor.fetchone()
                if not user_result:
                    return False
                user_id = user_result[0]

                cursor.execute(
                    "INSERT INTO groups (tg_group_id) VALUES (?) ON CONFLICT(tg_group_id) DO UPDATE SET tg_group_id = excluded.tg_group_id RETURNING id",
                    (user.tg_group_id,),
                )
                group_result = cursor.fetchone()
                if not group_result:
                    cursor.execute("SELECT id FROM groups WHERE tg_group_id = ?", (user.tg_group_id,))
                    group_result = cursor.fetchone()
                if not group_result:
                    return False
                group_id = group_result[0]

                existing = cursor.execute("SELECT 1 FROM users_groups WHERE user_id=? AND group_id=?", (user_id, group_id)).fetchone()
                if existing:
                    return False

                cursor.execute(
                    "INSERT INTO users_groups (user_id, group_id, permission) VALUES (?, ?, ?)", (user_id, group_id, user.permission.value)
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка добавления пользователя: {e}")
            return False

    def delete_user(self, user: User) -> bool:
        with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
            res = conn.execute(
                "DELETE FROM users_groups WHERE user_id=(SELECT id FROM users WHERE tg_user_id=?) AND group_id=(SELECT id FROM groups WHERE tg_group_id=?)",
                (user.tg_user_id, user.tg_group_id),
            )
            conn.commit()
            return res.rowcount > 0

    def get_user_by_username(self, username: str, tg_group_id: Optional[int] = None) -> Optional[User | List[User]]:
        with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            if username.startswith("@"):
                username = username[1:]
            if tg_group_id:
                result = conn.execute(
                    """
                    SELECT u.tg_user_id, ug.permission FROM users AS u
                    JOIN users_groups AS ug ON u.id = ug.user_id
                    JOIN groups AS g ON ug.group_id = g.id
                    WHERE u.username = ? AND g.tg_group_id = ?
                """,
                    (username, tg_group_id),
                ).fetchone()
                return (
                    User(tg_group_id=tg_group_id, tg_user_id=result[0], username=username, permission=PermissionLevel(result[1])) if result else None
                )
            else:
                results = conn.execute(
                    """
                    SELECT u.tg_user_id, u.username, g.tg_group_id, ug.permission FROM users AS u
                    JOIN users_groups AS ug ON u.id = ug.user_id
                    JOIN groups AS g ON ug.group_id = g.id WHERE u.username = ?
                """,
                    (username,),
                ).fetchall()
                return (
                    [User(tg_user_id=r[0], username=r[1], tg_group_id=r[2], permission=PermissionLevel(r[3])) for r in results] if results else None
                )

    def update_user_permission(self, user: User, new_permission: PermissionLevel) -> bool:
        with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
            res = conn.execute(
                "UPDATE users_groups SET permission=? WHERE user_id=(SELECT id FROM users WHERE tg_user_id=?) AND group_id=(SELECT id FROM groups WHERE tg_group_id=?)",
                (new_permission.value, user.tg_user_id, user.tg_group_id),
            )
            conn.commit()
            return res.rowcount > 0

    def get_users_in_group(self, tg_group_id: int) -> List[User]:
        with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            results = conn.execute(
                """
                SELECT u.tg_user_id, u.username, ug.permission FROM users AS u
                JOIN users_groups AS ug ON u.id = ug.user_id
                JOIN groups AS g ON ug.group_id = g.id WHERE g.tg_group_id = ?
            """,
                (tg_group_id,),
            ).fetchall()
            return [User(tg_user_id=r[0], username=r[1], permission=PermissionLevel(r[2]), tg_group_id=tg_group_id) for r in results]

    def check_username(self, tg_user_id: int, username: str) -> None:
        try:
            with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
                conn.execute("UPDATE users SET username=? WHERE tg_user_id=?", (username, tg_user_id))
                conn.commit()
        except Exception as e:
            logger.error(f"Ошибка обновления имени: {e}")

    def is_album_processed(self, media_group_id: str) -> bool:
        """Проверяет, обрабатывался ли уже этот альбом."""
        with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
            return conn.execute("SELECT 1 FROM processed_albums WHERE media_group_id=?", (media_group_id,)).fetchone() is not None

    def mark_album_processed(self, media_group_id: str) -> bool:
        """Атомарно помечает альбом. Возвращает True только если вставка прошла (мы первые)."""
        try:
            with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
                conn.execute("INSERT OR IGNORE INTO processed_albums (media_group_id, timestamp) VALUES (?, ?)", (media_group_id, time.time()))
                conn.commit()
                return True
        except Exception:
            return False

    def cleanup_old_albums(self, max_age_sec: int = 300) -> None:
        """Удаляет записи старше 5 минут, чтобы таблица не пухла."""
        cutoff = time.time() - max_age_sec
        with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
            conn.execute("DELETE FROM processed_albums WHERE timestamp < ?", (cutoff,))
            conn.commit()
