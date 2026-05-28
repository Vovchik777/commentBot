import sqlite3
import logging
import threading
from typing import Optional, List
from .models import User, PermissionLevel
from contextlib import closing

from src.shared.logger import get_bot_logger

logger = get_bot_logger()


class DataBaseManager:
    def __init__(self, db_file: str):
        self.db_file = db_file
        self.local = threading.local()
        self._init_db()
        logger.info(f"DatabaseManager инициализирован для файла: {db_file}")

    def _init_db(self) -> None:
        try:
            with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE,
                        tg_user_id INTEGER UNIQUE
                    )
                    """).fetchall()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS groups (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tg_group_id INTEGER UNIQUE
                    )
                    """).fetchall()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users_groups(
                        user_id INTEGER NOT NULL,
                        group_id INTEGER NOT NULL,
                        permission INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (user_id, group_id),
                        FOREIGN KEY (user_id) REFERENCES users(id),
                        FOREIGN KEY (group_id) REFERENCES groups(id)

                    )
                    """).fetchall()
                conn.commit()

        except sqlite3.Error as e:
            logger.error(f"Ошибка при создании таблицы users: {e}")
            raise

    def create_group_table(self, tg_group_id: int) -> None:
        try:
            with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute(
                    """
                    INSERT OR IGNORE INTO groups (tg_group_id) VALUES (?)
                    """,
                    (tg_group_id,),
                ).fetchall()
                conn.commit()
                logger.info(f"Таблица {tg_group_id} создана или уже существует")
        except Exception as e:
            logger.error(f"Ошибка создания таблицы {tg_group_id}: {e, e.__traceback__, e.__cause__, e.__context__}")
            raise

    def get_user(self, tg_user_id: int, tg_group_id: int) -> Optional[User]:
        try:
            with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                result = cursor.execute(
                    """
                    SELECT u.username, ug.permission 
                    FROM users AS u
                    JOIN users_groups AS ug ON u.id = ug.user_id
                    JOIN groups AS g ON ug.group_id = g.id
                    WHERE u.tg_user_id = ?
                    AND g.tg_group_id = ?
                    """,
                    (tg_user_id, tg_group_id),
                ).fetchone()

                if result:
                    return User(
                        tg_user_id=tg_user_id,
                        username=result[0],
                        permission=PermissionLevel(result[1]),
                        tg_group_id=tg_group_id,
                    )
                return None
        except sqlite3.OperationalError as e:
            logger.warning(f"Таблица для группы {tg_group_id} не существует: {e}")
            return None
        except Exception as e:
            logger.error(f"Ошибка получения пользователя {tg_user_id} из группы {tg_group_id}: {e}")
            return None

    def add_user(self, user: User) -> bool:
        try:
            with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
                conn.row_factory = sqlite3.Row
                self.create_group_table(user.tg_group_id)

                cursor = conn.cursor()

                # Вставляем или обновляем пользователя
                cursor.execute(
                    """
                    INSERT INTO users (username, tg_user_id) VALUES (?,?)
                    ON CONFLICT(tg_user_id) 
                    DO UPDATE SET username = excluded.username
                    RETURNING id
                    """,
                    (user.username, user.tg_user_id),
                )
                # ВАЖНО: fetchone() может вернуть None
                user_result = cursor.fetchone()

                if not user_result:
                    # Если не получили результат, значит что-то пошло не так
                    cursor.execute("SELECT id FROM users WHERE tg_user_id = ?", (user.tg_user_id,))
                    user_result = cursor.fetchone()

                    if not user_result:
                        logger.error(f"Не удалось найти или создать пользователя {user.tg_user_id}")
                        return False

                user_id = user_result[0]

                # Вставляем или получаем группу
                cursor.execute(
                    """
                    INSERT INTO groups (tg_group_id) VALUES (?)
                    ON CONFLICT(tg_group_id) 
                    DO UPDATE SET tg_group_id = excluded.tg_group_id
                    RETURNING id
                    """,
                    (user.tg_group_id,),
                )

                group_result = cursor.fetchone()
                if not group_result:
                    cursor.execute(
                        "SELECT id FROM groups WHERE tg_group_id = ?",
                        (user.tg_group_id,),
                    )
                    group_result = cursor.fetchone()
                    if not group_result:
                        logger.error(f"Не удалось найти или создать группу {user.tg_group_id}")
                        return False

                group_id = group_result[0]

                # Проверяем, существует ли уже связь пользователя с группой
                cursor.execute(
                    """
                    SELECT 1 FROM users_groups 
                    WHERE user_id = ? AND group_id = ?
                    """,
                    (user_id, group_id),
                ).fetchall()
                rowconut = cursor.rowcount > 0

                if rowconut:
                    logger.info(f"Пользователь {user.username} уже существует в группе {user.tg_group_id}")
                    return False

                # Создаем связь пользователя с группой
                cursor.execute(
                    """
                    INSERT INTO users_groups (user_id, group_id, permission)
                    VALUES (?, ?, ?)
                    """,
                    (user_id, group_id, user.permission.value),
                ).fetchall()
                conn.commit()
                success = cursor.rowcount > 0
                if success:
                    logger.info(f"Добавлен пользователь {user.username} (ID: {user.tg_user_id}) в группу {user.tg_group_id}")
                else:
                    logger.warning(f"Не удалось добавить пользователя {user.username} в группу {user.tg_group_id}")

                return success

        except sqlite3.IntegrityError as e:
            # Конфликт уникальности - пользователь уже в группе
            logger.info(f"Пользователь {user.username} уже существует в группе {user.tg_group_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка добавления пользователя {user.tg_user_id} в группу {user.tg_group_id}: {e}")
            self._get_connection().rollback()
            return False

    def delete_user(self, user: User) -> bool:
        try:
            with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
                conn.row_factory = sqlite3.Row

                cursor = conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM users_groups 
                    WHERE user_id = (SELECT id FROM users WHERE tg_user_id = ?)
                    AND group_id = (SELECT id FROM groups WHERE tg_group_id = ?)
                    RETURNING 1
                    """,
                    (user.tg_user_id, user.tg_group_id),
                ).fetchall()
                success = cursor.rowcount > 0
                logger.info(success)
                conn.commit()
                if success:
                    logger.info(
                        f"Удален пользователь {user.username} (ID: {user.tg_user_id}) из группы {user.tg_group_id}"
                        if user.tg_group_id
                        else (
                            f"Удален пользователь {user.username} (ID: {user.tg_user_id})"
                            if user.username
                            else (f"Удален пользователь с ID: {user.tg_user_id}" if user.tg_user_id else "Удален пользователь")
                        )
                    )
                else:
                    logger.warning(
                        f"Пользователь {user.username} (ID: {user.tg_user_id}) не найден в группе {user.tg_group_id}"
                        if user.tg_group_id
                        else (
                            f"Пользователь {user.username} (ID: {user.tg_user_id}) не найден"
                            if user.username
                            else (f"Пользователь с ID: {user.tg_user_id} не найден" if user.tg_user_id else "Пользователь не найден")
                        )
                    )

                return success
        except Exception as e:
            logger.error(f"Ошибка при удалении пользователя: {e}")
            return False

    def get_user_by_username(self, username: str, tg_group_id: Optional[int] = None) -> Optional[User | List[User]]:
        try:
            with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if username.startswith("@"):
                    username = username[1:]
                if tg_group_id:
                    result = cursor.execute(
                        """
                        SELECT u.tg_user_id, ug.permission
                        FROM users AS u
                        JOIN users_groups AS ug ON u.id = ug.user_id
                        JOIN groups AS g ON ug.group_id = g.id
                        WHERE u.username = ? AND g.tg_group_id = ?
                        """,
                        (username, tg_group_id),
                    ).fetchone()

                    if result:
                        return User(
                            tg_group_id=tg_group_id,
                            tg_user_id=result[0],
                            username=username,
                            permission=PermissionLevel(result[1]),
                        )
                else:
                    result = cursor.execute(
                        """
                        SELECT u.tg_user_id, u.username, g.tg_group_id, ug.permission
                        FROM users AS u
                        JOIN users_groups AS ug ON u.id = ug.user_id
                        JOIN groups AS g ON ug.group_id = g.id
                        WHERE u.username = ?
                        """,
                        (username,),
                    ).fetchall()

                    if result:
                        return [
                            User(
                                tg_user_id=row[0],
                                username=row[1],
                                tg_group_id=row[2],
                                permission=PermissionLevel(row[3]),
                            )
                            for row in result
                        ]
                return None
        except Exception as e:
            logger.error(f"Ошибка поиска пользователя по username {username}: {e}")
            return None

    def update_user_permission(self, user: User, new_permission: PermissionLevel) -> bool:
        try:
            with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE users_groups
                    SET permission = ?
                    WHERE user_id = (SELECT id FROM users WHERE tg_user_id = ?)
                    AND group_id = (SELECT id FROM groups WHERE tg_group_id = ?)
                    """,
                    (
                        new_permission.value,
                        user.tg_user_id,
                        user.tg_group_id,
                    ),
                ).fetchall()

                success = cursor.rowcount > 0
                conn.commit()
                if success:
                    logger.info(f"Обновлены права пользователя {user.tg_user_id} на {new_permission.name}")

                return success
        except Exception as e:
            logger.error(f"Ошибка обновления прав пользователя {user.tg_user_id}: {e}")
            return False

    def get_users_in_group(self, tg_group_id: int) -> List[User]:
        try:
            with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
                conn.row_factory = sqlite3.Row

                cursor = conn.cursor()

                results = cursor.execute(
                    """
                    SELECT u.tg_user_id, u.username, ug.permission
                    FROM users AS u
                    JOIN users_groups AS ug ON u.id = ug.user_id
                    JOIN groups AS g ON ug.group_id = g.id
                    WHERE g.tg_group_id = ?
                    """,
                    (tg_group_id,),
                ).fetchall()
                users = []
                for row in results:
                    users.append(
                        User(
                            tg_user_id=row[0],
                            username=row[1],
                            permission=PermissionLevel(row[2]),
                            tg_group_id=tg_group_id,
                        )
                    )

                return users
        except sqlite3.OperationalError:
            return []
        except Exception as e:
            logger.error(f"Ошибка получения пользователей группы {tg_group_id}: {e}")
            return []

    def check_username(self, tg_user_id: int, username: str) -> None:
        try:
            with closing(sqlite3.connect(self.db_file, timeout=10)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                        UPDATE users
                        SET username = ?
                        WHERE tg_user_id = ?
                        """,
                    (
                        username,
                        tg_user_id,
                    ),
                ).fetchall()
                conn.commit()
        except Exception as e:
            logger.error(f"Ошибка проверки имени пользователя {tg_user_id}: {e}")
