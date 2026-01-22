import logging
from typing import List, Tuple
from database.manager import DataBaseManager
from database.models import User, PermissionLevel
from config import Config
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseUpdater:
    def __init__(self, config: Config):
        self.config = config
        self.db = DataBaseManager(config.DB_FILE)
        self.base_url = f"https://api.telegram.org/bot{config.BOT_TOKEN}"
        self.logger_chat_id = config.LOGGER_CHAT_ID

    def get_all_groups(self) -> List[str]:
        """Получить список всех таблиц групп из базы данных"""
        cursor = self.db._get_cursor()
        try:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'group_%'"
            )
            tables = [row[0] for row in cursor.fetchall()]
            logger.info(f"Найдено таблиц: {len(tables)}")
            return tables
        except Exception as e:
            logger.error(f"Ошибка получения списка таблиц: {e}")
            return []

    def get_all_users_from_table(self, table_name: str) -> List[Tuple[int, str]]:
        """Получить всех пользователей из конкретной таблицы"""
        cursor = self.db._get_cursor()
        try:
            cursor.execute(f"SELECT user_id, username FROM {table_name}")
            users = [(row[0], row[1]) for row in cursor.fetchall()]
            return users
        except Exception as e:
            logger.error(f"Ошибка получения пользователей из таблицы {table_name}: {e}")
            return []

    def get_user_info_from_telegram(self, user_id: int) -> dict:
        """Получить информацию о пользователе через Telegram API"""
        url = f"{self.base_url}/getChat"
        payload = {"chat_id": user_id}

        try:
            response = requests.post(url, json=payload, timeout=10)
            result = response.json()

            if result.get("ok"):
                return result.get("result", {})
            else:
                logger.error(f"Ошибка Telegram API: {result}")
                return {}
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса к Telegram API: {e}")
            return {}
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")
            return {}

    def update_username_in_db(
        self, table_name: str, user_id: int, old_username: str, new_username: str
    ) -> bool:
        """Обновить имя пользователя в базе данных"""
        cursor = self.db._get_cursor()
        try:
            cursor.execute(
                f"UPDATE {table_name} SET username = ? WHERE user_id = ?",
                (new_username, user_id),
            )
            self.db._get_connection().commit()

            success = cursor.rowcount > 0
            if success:
                logger.info(
                    f"Обновлен username: {old_username} ({user_id}) -> @{new_username}"
                )
            return success
        except Exception as e:
            logger.error(f"Ошибка обновления username в БД: {e}")
            return False

    def send_update_notification(
        self, old_username: str, new_username: str, user_id: int
    ) -> None:
        """Отправить уведомление в лог-чат об обновлении"""
        message = f"Обновлен пользователь @{old_username} на @{new_username}, user_id={user_id}"

        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.logger_chat_id,
                "text": message,
                "parse_mode": "HTML",
            }
            response = requests.post(url, json=payload, timeout=10)

            if not response.json().get("ok"):
                logger.warning(f"Не удалось отправить уведомление: {response.json()}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")

    def update_all_users(self) -> None:
        """Основная функция обновления всех пользователей"""
        tables = self.get_all_groups()

        if not tables:
            logger.warning("Не найдено таблиц групп для обновления")
            return

        total_updates = 0
        total_users = 0

        for table_name in tables:
            logger.info(f"Обработка таблицы: {table_name}")
            users = self.get_all_users_from_table(table_name)

            if not users:
                logger.info(f"В таблице {table_name} нет пользователей")
                continue

            for user_id, old_username in users:
                total_users += 1

                # Пропускаем если username уже правильный (начинается с @)
                if old_username and old_username.startswith("@"):
                    continue

                # Получаем актуальную информацию из Telegram
                user_info = self.get_user_info_from_telegram(user_id)

                if not user_info:
                    logger.warning(
                        f"Не удалось получить информацию для user_id={user_id}"
                    )
                    continue

                current_username = user_info.get("username")

                # Если username отсутствует или не изменился
                if not current_username or current_username == old_username:
                    continue

                # Обновляем в базе данных
                if self.update_username_in_db(
                    table_name, user_id, old_username, current_username
                ):
                    total_updates += 1
                    self.send_update_notification(
                        old_username or "без username", current_username, user_id
                    )

            # Небольшая пауза между таблицами чтобы не перегружать API
            import time

            time.sleep(0.5)

        logger.info(
            f"Обновление завершено. Обработано пользователей: {total_users}, обновлено: {total_updates}"
        )

        # Отправляем итоговый отчет
        if total_updates > 0:
            self.send_final_report(total_users, total_updates)

    def send_final_report(self, total_users: int, total_updates: int) -> None:
        """Отправить итоговый отчет об обновлении"""
        message = (
            f"📊 <b>Отчет об обновлении пользователей</b>\n"
            f"────────────────\n"
            f"👥 Всего пользователей: <code>{total_users}</code>\n"
            f"🔄 Обновлено username: <code>{total_updates}</code>\n"
            f"📈 Процент обновлений: <code>{(total_updates/total_users*100 if total_users > 0 else 0):.1f}%</code>\n"
            f"\n"
            f"✅ Обновление завершено успешно!"
        )

        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.logger_chat_id,
                "text": message,
                "parse_mode": "HTML",
            }
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Ошибка отправки итогового отчета: {e}")


def main():
    """Точка входа скрипта"""
    try:
        # Инициализация конфигурации
        config = Config()
        config.validate()

        # Создание и запуск апдейтера
        updater = DatabaseUpdater(config)

        logger.info("Начинаю обновление базы данных пользователей...")
        updater.update_all_users()

        logger.info("Обновление успешно завершено!")

    except Exception as e:
        logger.error(f"Критическая ошибка при обновлении: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
