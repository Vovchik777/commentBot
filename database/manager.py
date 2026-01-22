import sqlite3
import logging
import threading
from typing import Optional, List
from .models import User, PermissionLevel

logger = logging.getLogger(__name__)


class DataBaseManager:
    def __init__(self, db_file: str):
        self.db_file = db_file
        self.local = threading.local()
        logger.info(f"DatabaseManager инициализирован для файла: {db_file}")

    def _get_connection(self):
        if not hasattr(self.local, "conn") or self.local.conn is None:
            self.local.conn = sqlite3.connect(
                self.db_file, check_same_thread=False, timeout=10.0
            )
            self.local.conn.row_factory = sqlite3.Row
        return self.local.conn

    def _get_cursor(self):
        conn = self._get_connection()
        return conn.cursor()

    def create_group_table(self, group_id: int) -> None:
        table_name = f"group_{abs(group_id)}"
        cursor = self._get_cursor()
        try:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    permission INTEGER DEFAULT 0
                )
            """
            )
            self._get_connection().commit()
            logger.info(f"Таблица {table_name} создана или уже существует")
        except Exception as e:
            logger.error(f"Ошибка создания таблицы {table_name}: {e}")
            raise

    def get_user(self, user_id: int, group_id: int) -> Optional[User]:
        try:
            table_name = f"group_{abs(group_id)}"
            cursor = self._get_cursor()

            result = cursor.execute(
                f"SELECT user_id, username, permission FROM {table_name} WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            if result:
                return User(
                    user_id=result[0],
                    username=result[1],
                    permission=PermissionLevel(result[2]),
                    group_id=group_id,
                )
            return None
        except sqlite3.OperationalError as e:
            logger.warning(f"Таблица для группы {group_id} не существует: {e}")
            return None
        except Exception as e:
            logger.error(
                f"Ошибка получения пользователя {user_id} из группы {group_id}: {e}"
            )
            return None

    def add_user(self, user: User) -> bool:

        try:
            self.create_group_table(user.group_id)

            cursor = self._get_cursor()
            cursor.execute(
                f"""
                INSERT OR IGNORE INTO {user.table_name} 
                (user_id, username, permission) 
                VALUES (?, ?, ?)
                """,
                (user.user_id, user.username, user.permission.value),
            )
            self._get_connection().commit()

            success = cursor.rowcount > 0
            if success:
                logger.info(
                    f"Добавлен пользователь {user.username} (ID: {user.user_id}) в группу {user.group_id}"
                )
            else:
                logger.info(
                    f"Пользователь {user.username} уже существует в группе {user.group_id}"
                )

            return success
        except Exception as e:
            logger.error(
                f"Ошибка добавления пользователя {user.user_id} в группу {user.group_id}: {e}"
            )
            return False

    def delete_user(self, user: User) -> bool:
        try:
            cursor = self._get_cursor()
            cursor.execute(
                f"DELETE FROM {user.table_name} WHERE user_id = ?",
                (user.user_id,),
            )
            self._get_connection().commit()
            success = cursor.rowcount > 0
            if success:
                logger.info(
                    f"Удален пользователь {user.username} (ID: {user.user_id}) из группы {user.group_id}"
                    if user.group_id
                    else (
                        f"Удален пользователь {user.username} (ID: {user.user_id})"
                        if user.username
                        else (
                            f"Удален пользователь с ID: {user.user_id}"
                            if user.user_id
                            else "Удален пользователь"
                        )
                    )
                )
            else:
                logger.warning(
                    f"Пользователь {user.username} (ID: {user.user_id}) не найден в группе {user.group_id}"
                    if user.group_id
                    else (
                        f"Пользователь {user.username} (ID: {user.user_id}) не найден"
                        if user.username
                        else (
                            f"Пользователь с ID: {user.user_id} не найден"
                            if user.user_id
                            else "Пользователь не найден"
                        )
                    )
                )

            return success
        except Exception as e:
            logger.error(f"Ошибка при удалении пользователя: {e}")
            return False

    def get_user_by_username(
        self, username: str, group_id: Optional[int] = None
    ) -> Optional[User]:
        try:
            if username.startswith("@"):
                username = username[1:]

            cursor = self._get_cursor()

            if group_id:
                table_name = f"group_{abs(group_id)}"
                result = cursor.execute(
                    f"SELECT user_id, username, permission FROM {table_name} WHERE username = ?",
                    (username,),
                ).fetchone()

                if result:
                    return User(
                        user_id=result[0],
                        username=result[1],
                        permission=PermissionLevel(result[2]),
                        group_id=group_id,
                    )
            else:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'group_%'"
                )
                tables = [row[0] for row in cursor.fetchall()]

                for table_name in tables:
                    result = cursor.execute(
                        f"SELECT user_id, username, permission FROM {table_name} WHERE username = ?",
                        (username,),
                    ).fetchone()
                    if result:
                        group_id_from_table = int(table_name.split("_")[1])
                        return User(
                            user_id=result[0],
                            username=result[1],
                            permission=PermissionLevel(result[2]),
                            group_id=group_id_from_table,
                        )

            return None
        except Exception as e:
            logger.error(f"Ошибка поиска пользователя по username {username}: {e}")
            return None

    def update_user_permission(
        self, user: User, new_permission: PermissionLevel
    ) -> bool:
        try:
            cursor = self._get_cursor()
            cursor.execute(
                f"UPDATE {user.table_name} SET permission = ? WHERE user_id = ?",
                (new_permission.value, user.user_id),
            )
            self._get_connection().commit()

            success = cursor.rowcount > 0
            if success:
                logger.info(
                    f"Обновлены права пользователя {user.user_id} на {new_permission.name}"
                )

            return success
        except Exception as e:
            logger.error(f"Ошибка обновления прав пользователя {user.user_id}: {e}")
            return False

    def get_all_users_in_group(self, group_id: int) -> List[User]:
        try:
            table_name = f"group_{abs(group_id)}"
            cursor = self._get_cursor()

            results = cursor.execute(
                f"SELECT user_id, username, permission FROM {table_name} ORDER BY permission DESC"
            ).fetchall()

            users = []
            for row in results:
                users.append(
                    User(
                        user_id=row[0],
                        username=row[1],
                        permission=PermissionLevel(row[2]),
                        group_id=group_id,
                    )
                )

            return users
        except sqlite3.OperationalError:
            return []
        except Exception as e:
            logger.error(f"Ошибка получения пользователей группы {group_id}: {e}")
            return []
