from datetime import time
import logging
import re
import threading
from typing import Any, Dict, List, Optional

import requests

from config import Config
from database.manager import DataBaseManager
from services.commentManager import CommentsManager
from services.logsManager import LogsManager
from utils.time_utils import get_moscow_datetime_str, get_moscow_now
from .handlers import MessageHandler
from storage.banwords import banwords

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, config: Config):
        self.config = config
        self.base_url = f"https://api.telegram.org/bot{config.BOT_TOKEN}"
        self.db = DataBaseManager(config.DB_FILE)
        self.comments_manager = CommentsManager(config.COMMENTS_FILE)
        self.logs_manager = LogsManager(config.LOGGED_MSGS_FILE)
        self.lock = threading.Lock()
        self.handler = MessageHandler(self)

        self.processed_media_groups = {}
        self.album_types = {}
        self.album_timestamps = {}

        self.prev_comment = ""

        logger.info("TelegramBot инициализирован")

    def handle_forwarded_message(self, message_data: Dict[str, Any]) -> None:
        try:
            chat_id = message_data["chat"]["id"]
            message_id = message_data["message_id"]

            self.set_message_reaction(chat_id, message_id)

            is_media = any(
                key in message_data for key in ["photo", "video", "document", "audio"]
            )

            if is_media:
                media_group_id = message_data.get("media_group_id")
                if media_group_id:
                    if not hasattr(self, "album_types"):
                        self.album_types = {}

                    has_caption = bool(message_data.get("caption"))
                    album_type = self.album_types.get(media_group_id)

                    if has_caption:
                        self.album_types[media_group_id] = "with_caption"
                        logger.info(f"Альбом с подписью: {media_group_id}")
                    elif not has_caption and not album_type:
                        self.album_types[media_group_id] = "without_caption"
                        logger.info(f"Альбом без подписи: {media_group_id}")
                    elif not has_caption and album_type:
                        logger.info("Продолжение альбома, пропускаем")
                        return

            current_time = get_moscow_now()
            if not hasattr(self, "album_timestamps"):
                self.album_timestamps = {}

            self.album_timestamps[media_group_id] = current_time

            for mgid in list(self.album_types.keys()):
                if (
                    mgid not in self.album_timestamps
                    or (current_time - self.album_timestamps[mgid]).total_seconds() > 30
                ):
                    if mgid in self.album_types:
                        del self.album_types[mgid]
                    if mgid in self.album_timestamps:
                        del self.album_timestamps[mgid]

            self.send_comment_to_message(chat_id, message_id, is_media)

            self.check_scheduled_comments(chat_id, message_id)

        except Exception as e:
            logger.error(f"Ошибка обработки пересланного сообщения: {e}")

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: int = None,
        reply_markup: Optional[Dict] = None,
        parse_mode: str = "HTML",
    ) -> Optional[Dict]:
        MAX_LENGHT = 4096

        if len(text) <= MAX_LENGHT:
            return self._send_single_message(
                chat_id, text, reply_to_message_id, reply_markup, parse_mode
            )
        else:
            return self._send_long_message(
                chat_id, text, reply_to_message_id, parse_mode
            )

    def _send_single_message(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: Optional[int],
        reply_markup: Optional[Dict],
        parse_mode: str,
    ) -> Dict:
        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}

        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get("ok"):
                logger.info(f"Сообщение отправлено в чат {chat_id}: {text[:50]}...")
            else:
                logger.error(f"Ошибка Telegram API: {result}")

            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
            return {"ok": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Неожиданная ошибка при отправке: {e}")
            return {"ok": False, "error": str(e)}

    def _send_long_message(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: Optional[int],
        parse_mode: str,
    ) -> List[Dict]:
        parts = []
        current_part = ""
        lines = text.split("\n")

        for line in lines:
            if len(current_part) + len(line) + 1 <= 4096:
                current_part += line + "\n"
            else:
                if current_part:
                    parts.append(current_part.strip())
                current_part = line + "\n"

        if current_part:
            parts.append(current_part.strip())

        results = []
        for i, part in enumerate(parts):
            logger.info(f"Отправка части {i+1}/{len(parts)} ({len(part)} символов)")

            result = self._send_single_message(
                chat_id, part, reply_to_message_id, None, parse_mode
            )

            results.append(result)

            if i < len(parts) - 1:
                time.sleep(0.3)

        return results

    def set_message_reaction(
        self, chat_id: int, message_id: int, emoji: str = "🗿"
    ) -> Dict:
        url = f"{self.base_url}/setMessageReaction"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reaction": [{"type": "emoji", "emoji": emoji}],
        }

        try:
            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 429:
                retry_after = (
                    response.json().get("parameters", {}).get("retry_after", 5)
                )
                logger.warning(f"Rate limit exceeded. Waiting {retry_after} seconds.")
                time.sleep(retry_after)
                return self.set_message_reaction(chat_id, message_id, emoji)

            response.raise_for_status()
            result = response.json()

            if result.get("ok"):
                logger.info(
                    f"Реакция установлена на сообщение {message_id} в чате {chat_id}"
                )
            else:
                logger.warning(f"Не удалось установить реакцию: {result}")

            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка установки реакции: {e}")
            return {"ok": False, "error": str(e)}

    def get_chat_info(self, chat_id: int) -> Dict[str, Any]:
        url = f"{self.base_url}/getChat"
        payload = {"chat_id": chat_id}

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get("ok"):
                return result.get("result", {})
            else:
                logger.error(f"Ошибка получения информации о чате {chat_id}: {result}")
                return {}
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса getChat для {chat_id}: {e}")
            return {}

    def get_user_info(self, user_id: int) -> Dict[str, Any]:
        return self.get_chat_info(user_id)

    def send_comment_to_message(
        self, chat_id: int, message_id: int, is_media: bool = False
    ) -> Optional[Dict]:
        try:
            comment_type = "photo" if is_media else "text"

            comment = self.comments_manager.get_random_comment(chat_id, comment_type)

            if comment == self.prev_comment:
                comment = self._get_different_comment(chat_id, comment_type, comment)

            comment = self.comments_manager.parse_comment_template(comment)

            self.prev_comment = comment

            logger.info(f"Отправка комментария в чат {chat_id}: {comment}")
            return self.send_message(
                chat_id=chat_id, text=comment, reply_to_message_id=message_id
            )

        except Exception as e:
            logger.error(f"Ошибка отправки комментария: {e}")
            return None

    def _get_different_comment(
        self, chat_id: int, comment_type: str, current_comment: str
    ) -> str:
        group_name = f"group_{abs(chat_id)}"
        comments_data = self.comments_manager.comment_data.get(group_name, {})

        if comment_type == "photo":
            available = comments_data.get("photo", [])
        else:
            available = comments_data.get("text", [])

        if len(available) <= 1:
            return current_comment

        attempts = 0
        max_attempts = min(10, len(available) * 2)

        while attempts < max_attempts:
            new_comment = self.comments_manager.get_random_comment(
                chat_id, comment_type
            )
            if new_comment != current_comment:
                return new_comment
            attempts += 1

        return current_comment

    def process_update(self, update: Dict[str, Any]) -> None:

        logger.info(f"Получено обновление: {list(update.keys())}")

        try:
            if "message" in update:
                self.handler.process_message(update["message"])
            elif "edited_message" in update:
                logger.info("Получено редактированное сообщение")
            elif "callback_query" in update:
                logger.info("Получен callback query")
            else:
                logger.info(f"Обновление другого типа: {list(update.keys())}")

        except Exception as e:
            logger.error(f"Ошибка обработки обновления: {e}", exc_info=True)

    def check_scheduled_comments(self, chat_id: int, message_id: int) -> None:
        try:

            today = get_moscow_datetime_str()
            group_name = f"group_{abs(chat_id)}"

            scheduled = self.comments_manager.comment_data.get(group_name, {}).get(
                "scheduled", {}
            )

            if today in scheduled:
                logger.info(f"Найдены запланированные комментарии на сегодня ({today})")

                for comment in scheduled[today]:

                    comment = self.comments_manager.parse_comment_template(comment)

                    self.send_message(
                        chat_id=chat_id, text=comment, reply_to_message_id=message_id
                    )

                    time.sleep(0.5)

        except Exception as e:
            logger.error(f"Ошибка проверки запланированных комментариев: {e}")

    def check_banwords(self, message_data: dict) -> bool:
        chat_id = message_data["chat"]["id"]
        text = message_data.get("text", "").lower()
        message_id = message_data["message_id"]
        for key in banwords.keys():
            if re.search(key, text, re.IGNORECASE):
                self.send_message(
                    chat_id, banwords.get(key, "нельзя"), reply_to_message_id=message_id
                )

    def cleanup_processed_media_groups(self, max_age_seconds: int = 300) -> None:
        current_time = time.time()
        expired_keys = []

        for media_group_id, timestamp in self.processed_media_groups.items():
            if current_time - timestamp > max_age_seconds:
                expired_keys.append(media_group_id)

        for key in expired_keys:
            del self.processed_media_groups[key]

        for key in list(self.album_types.keys()):
            if key not in self.processed_media_groups:
                del self.album_types[key]
                if key in self.album_timestamps:
                    del self.album_timestamps[key]

    def close(self) -> None:
        logger.info("Закрытие TelegramBot")

        if hasattr(self, "db"):
            self.db.close()

        logger.info("TelegramBot закрыт")

    def __del__(self):
        try:
            self.close()
        except:
            pass
