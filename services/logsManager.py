import datetime
import json
import logging
import os
import utils.time_utils
from typing import Optional, Dict, Any

import pytz

logger = logging.getLogger(__name__)


class LogsManager:
    def __init__(self, logs_file: str):
        self.logs_file = logs_file

        self.logged_msgs = {}
        self.load_logs()

    def load_logs(self) -> None:
        try:
            if os.path.exists(self.logs_file):
                with open(self.logs_file, "r", encoding="utf-8") as file:
                    self.logged_msgs = json.load(file)

        except Exception as e:
            logger.error(f"Error loading logs: {e}")

    def save_logs(self) -> None:
        try:
            with open(self.logs_file, "w", encoding="utf-8") as f:
                json.dump(self.logged_msgs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving logs: {e}")

    def add_message_log(
        self, bot_msg_id: int, chat_id: int, message_id: int, text: str
    ) -> Optional[Dict[str, Any]]:

        current_time: datetime.datetime = utils.time_utils.get_moscow_now()

        self.logged_msgs[str(bot_msg_id)] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "timestamp": current_time,
        }
        self.save_logs()

    def get_message_info(self, bot_msg_id: int) -> Optional[Dict[str, Any]]:
        return self.logged_msgs.get(str(bot_msg_id))

    def cleanup_old_logs(self) -> int:
        current_time = utils.time_utils.get_moscow_now()
        keys_to_remove = []

        for key, value in self.logged_msgs.items():
            if (current_time - value.get("timestamp", 0)) > 24 * 60 * 60:
                keys_to_remove.append(key)
                logger.info(f"Removing old log: {key}")

        for key in keys_to_remove:
            del self.logged_msgs[key]

        if keys_to_remove:
            self.save_logs()
        return len(keys_to_remove)
