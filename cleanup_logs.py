import os
import sys
import datetime
import pytz
import requests

moscow_tz = pytz.timezone("Europe/Moscow")
import json
import time
import logging
from config import Config
from services.logsManager import LogsManager

# sys.path.append(os.path.dirname(os.path.abspath(__file__)))

cfg = Config()
cfg.validate()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cleanup_task():
    try:
        if os.path.exists(cfg.LOGGED_MSGS_FILE):
            with open(cfg.LOGGED_MSGS_FILE, "r", encoding="utf-8") as f:
                logged_msgs = json.load(f)
        else:
            logged_msgs = {}

        keys_to_remove = LogsManager(cfg.LOGGED_MSGS_FILE).cleanup_old_logs()

        if keys_to_remove == -1:
            logger.error("keys_to_remove == -1")
            return

        logger.info(f"удалено {keys_to_remove} старых логов")
        logger.info(f"{logged_msgs}")
        logger.info(f"осталось {len(logged_msgs)}")

        if keys_to_remove:
            BOT_TOKEN = cfg.BOT_TOKEN
            LOGGER_CHAT_ID = cfg.LOGGER_CHAT_ID
            if BOT_TOKEN and LOGGER_CHAT_ID:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": LOGGER_CHAT_ID,
                    "text": f"удалено {keys_to_remove} старых логов\nОсталось {len(logged_msgs)}",
                }
                requests.post(url, json=payload)
                logger.info("уведомление отправлено в логгер чат")

            else:
                logger.warning(
                    "не удалось отправить уведомление в логгер чат: отсутствует токен или ID"
                )

    except Exception as e:
        logger.error(f"Ошибка при очистке: {e}")


if __name__ == "__main__":
    cleanup_task()
