import json
import os
import sqlite3
import time
import threading
from typing import Any, Dict, Optional, List, Tuple
from contextlib import closing
from src.config import Config
from .models import Banword, Comment, CommentTypes, User, PermissionLevel
from src.shared.logger import get_db_logger

logger = get_db_logger()
config = Config()


class DataBaseManager:
    def __init__(self, db_file: str):
        self.db_file = db_file
        self._init_db()
        self._start_ttl_worker()
        logger.info(f"DatabaseManager инициализирован для файла: {db_file}")

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.db_file)), exist_ok=True)
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
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
                timestamp REAL NOT NULL,
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS banwords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                pattern TEXT NOT NULL,
                reply_text TEXT NOT NULL,
                UNIQUE(group_id, pattern)
            );
            CREATE TABLE IF NOT EXISTS banwords_cache (
                group_id INTEGER PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS last_comments (
                chat_id INTEGER PRIMARY KEY,
                comment_text TEXT NOT NULL,
                updated_at REAL NOT NULL
            );

            
            CREATE INDEX IF NOT EXISTS idx_albums_expire ON processed_albums(expires_at);
            CREATE INDEX IF NOT EXISTS idx_comments_lookup ON comments(group_id, comment_type);
            CREATE INDEX IF NOT EXISTS idx_comments_scheduled ON comments(group_id, scheduled_date);
            CREATE INDEX IF NOT EXISTS idx_logs_lookup ON message_logs(original_message_id);
            CREATE INDEX IF NOT EXISTS idx_logs_cleanup ON message_logs(timestamp);
            CREATE INDEX IF NOT EXISTS idx_banwords_group ON banwords(group_id);
            CREATE INDEX IF NOT EXISTS idx_banwords_cache_expire ON banwords_cache(expires_at);
            """)
            conn.commit()

    def _start_ttl_worker(self) -> None:
        def cleanup_task():
            while True:
                try:
                    with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
                        now = time.time()
                        conn.execute("DELETE FROM processed_albums WHERE expires_at < ?", (now,))
                        conn.execute("DELETE FROM banwords_cache WHERE expires_at < ?", (now,))
                        conn.commit()
                except Exception as e:
                    logger.error(f"TTL Worker error: {e}")
                time.sleep(60)

        self.worker = threading.Thread(target=cleanup_task, daemon=True)
        self.worker.start()

    def create_group_table(self, tg_group_id: int) -> None:
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
            conn.execute("INSERT OR IGNORE INTO groups (tg_group_id) VALUES (?)", (tg_group_id,))
            conn.commit()

    def get_user(self, tg_user_id: int, tg_group_id: int) -> Optional[User]:
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
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
            with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
                conn.row_factory = sqlite3.Row
                self.create_group_table(user.tg_group_id)
                cursor = conn.cursor()

                cursor.execute(
                    "INSERT INTO users (username, tg_user_id) VALUES (?, ?) "
                    "ON CONFLICT(tg_user_id) DO UPDATE SET username = excluded.username "
                    "RETURNING id",
                    (user.username, user.tg_user_id),
                )
                user_id = cursor.fetchone()[0]

                cursor.execute(
                    "INSERT INTO groups (tg_group_id) VALUES (?) "
                    "ON CONFLICT(tg_group_id) DO UPDATE SET tg_group_id = excluded.tg_group_id "
                    "RETURNING id",
                    (user.tg_group_id,),
                )
                group_id = cursor.fetchone()[0]

                existing = cursor.execute(
                    "SELECT 1 FROM users_groups WHERE user_id=? AND group_id=?",
                    (user_id, group_id),
                ).fetchone()

                if existing:
                    conn.commit()
                    return False

                cursor.execute(
                    "INSERT INTO users_groups (user_id, group_id, permission) VALUES (?, ?, ?)",
                    (user_id, group_id, user.permission.value),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка добавления пользователя: {e}")
            return False

    def delete_user(self, user: User) -> bool:
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
            res = conn.execute(
                "DELETE FROM users_groups WHERE user_id=(SELECT id FROM users WHERE tg_user_id=?) AND group_id=(SELECT id FROM groups WHERE tg_group_id=?)",
                (user.tg_user_id, user.tg_group_id),
            )
            conn.commit()
            return res.rowcount > 0

    def get_user_by_username(self, username: str, tg_group_id: Optional[int] = None) -> Optional[User | List[User]]:
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
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
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
            res = conn.execute(
                "UPDATE users_groups SET permission=? WHERE user_id=(SELECT id FROM users WHERE tg_user_id=?) AND group_id=(SELECT id FROM groups WHERE tg_group_id=?)",
                (new_permission.value, user.tg_user_id, user.tg_group_id),
            )
            conn.commit()
            return res.rowcount > 0

    def get_users_in_group(self, tg_group_id: int) -> List[User]:
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
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
            with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
                conn.execute("UPDATE users SET username=? WHERE tg_user_id=?", (username, tg_user_id))
                conn.commit()
        except Exception as e:
            logger.error(f"Ошибка обновления имени: {e}")

    # --- АЛЬБОМЫ ---
    def is_album_processed(self, media_group_id: str) -> bool:
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_albums WHERE media_group_id=? AND expires_at > ?",
                (media_group_id, time.time()),
            ).fetchone()
            return row is not None

    def mark_album_processed(self, media_group_id: str) -> bool:
        try:
            now = time.time()
            expires_at = now + config.TTL_ALBUM_PROCESSED
            with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO processed_albums (media_group_id, timestamp, expires_at) VALUES (?, ?, ?)",
                    (media_group_id, now, expires_at),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception:
            return False

    # --- COMMENTS ---
    def add_comment(self, comment: Comment) -> bool:
        if comment.comment_type == CommentTypes.SCHEDULED and comment.scheduled_date is None:
            return False
        try:
            with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO comments
                        (group_id, comment_type, comment_text, scheduled_date, use_count)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        comment.group_id,
                        comment.comment_type.value,
                        comment.comment_text,
                        comment.scheduled_date,
                        comment.use_count,
                    ),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка добавления комментария: {e}")
            return False

    def delete_comment(self, group_id: int, comment_type: CommentTypes, index: int) -> Optional[Comment]:
        if index < 1:
            return None
        order = "ORDER BY scheduled_date, id" if comment_type == CommentTypes.SCHEDULED else "ORDER BY id"
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT id, group_id, comment_type, comment_text, scheduled_date, use_count
                FROM comments
                WHERE group_id=? AND comment_type=?
                {order}
                LIMIT 1 OFFSET ?
                """,
                (group_id, comment_type.value, index - 1),
            ).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM comments WHERE id=?", (row["id"],))
            conn.commit()
            return self._row_to_comment(row)

    def get_random_comment(self, group_id: int, comment_type: CommentTypes) -> Optional[Comment]:
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT group_id, comment_type, comment_text, scheduled_date, use_count
                FROM comments
                WHERE group_id=? AND comment_type=?
                ORDER BY RANDOM()
                LIMIT 1
                """,
                (group_id, comment_type.value),
            ).fetchone()
            return self._row_to_comment(row) if row else None

    def get_scheduled_for_today(self, group_id: int, today_str: str) -> List[Comment]:
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT group_id, comment_type, comment_text, scheduled_date, use_count
                FROM comments
                WHERE group_id=? AND comment_type=? AND scheduled_date=?
                """,
                (group_id, CommentTypes.SCHEDULED.value, today_str),
            ).fetchall()
            return [self._row_to_comment(r) for r in rows]

    def get_comments_list(self, group_id: int) -> Dict[str, Any]:
        result: Dict[str, Any] = {"text": [], "photo": [], "scheduled": {}}
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT group_id, comment_type, comment_text, scheduled_date, use_count
                FROM comments
                WHERE group_id=?
                ORDER BY id
                """,
                (group_id,),
            ).fetchall()
            for row in rows:
                comment = self._row_to_comment(row)
                if comment.comment_type == CommentTypes.SCHEDULED:
                    if comment.scheduled_date is None or comment.scheduled_date == "":
                        continue
                    result["scheduled"].setdefault(comment.scheduled_date, []).append(comment)
                elif comment.comment_type.value in result:
                    result[comment.comment_type.value].append(comment)
                else:
                    logger.warning(f"Неизвестный тип комментария: {comment.comment_type}")
        return result

    def get_banwords_list(self, group_id: int) -> List[Banword]:
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT group_id, pattern, reply_text
                FROM banwords
                WHERE group_id = ?
                """,
                (group_id,),
            ).fetchall()
        return [self._row_to_banword(row) for row in rows]

    def add_banword(self, group_id: int, pattern: str, reply: str) -> bool:
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
            try:
                conn.execute(
                    "INSERT INTO banwords (group_id, pattern, reply_text) VALUES (?, ?, ?)",
                    (group_id, pattern, reply),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError as e:
                logger.warning(f"Банворд не добавлен: {e}")
                return False

    def get_banwords_cache(self, group_id: int) -> Optional[Tuple[List[Banword], float]]:
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
            row = conn.execute(
                "SELECT payload, expires_at FROM banwords_cache WHERE group_id=? AND expires_at > ?",
                (group_id, time.time()),
            ).fetchone()
        if not row:
            return None
        return [Banword(group_id, p, r) for p, r in json.loads(row[0])], row[1]

    def set_banwords_cache(self, group_id: int, banwords: List[Banword], ttl: int) -> float:
        payload = json.dumps([[b.pattern, b.reply] for b in banwords])
        now = time.time()
        expires_at = now + ttl
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO banwords_cache (group_id, payload, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (group_id, payload, now, expires_at),
            )
            conn.commit()
        return expires_at

    def invalidate_banwords_cache(self, group_id: Optional[int] = None) -> None:
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
            if group_id is None:
                conn.execute("DELETE FROM banwords_cache")
            else:
                conn.execute("DELETE FROM banwords_cache WHERE group_id=?", (group_id,))
            conn.commit()

    def get_last_comment(self, chat_id: int) -> Optional[str]:
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
            row = conn.execute(
                "SELECT comment_text FROM last_comments WHERE chat_id=?",
                (chat_id,),
            ).fetchone()
            return row[0] if row else None

    def set_last_comment(self, chat_id: int, text: str) -> None:
        with closing(sqlite3.connect(self.db_file, timeout=config.DB_CONNECTION_TIMEOUT)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO last_comments (chat_id, comment_text, updated_at)
                VALUES (?, ?, ?)
                """,
                (chat_id, text, time.time()),
            )
            conn.commit()

    @staticmethod
    def _row_to_comment(row: sqlite3.Row) -> Comment:
        return Comment(
            group_id=row["group_id"],
            comment_type=row["comment_type"],
            comment_text=row["comment_text"],
            scheduled_date=row["scheduled_date"],
            use_count=row["use_count"],
        )

    @staticmethod
    def _row_to_banword(row: sqlite3.Row) -> Banword:
        return Banword(
            group_id=row["group_id"],
            pattern=row["pattern"],
            reply=row["reply_text"]
        )