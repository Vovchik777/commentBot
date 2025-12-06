import os
import sys
import datetime
import pytz
import requests

moscow_tz = pytz.timezone("Europe/Moscow")
import json
import time
import logging

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup_task():
    try:
        if os.path.exists("logged_msgs.json"):
            with open("logged_msgs.json", "r", encoding="utf-8") as f:
                logged_msgs = json.load(f)
        else:
            logged_msgs = {}

        current_time = time.time()
        keys_to_remove = []
        for key, value in logged_msgs.items():
            if (current_time - value.get("timestamp", 0)) > 24 * 60 * 60:
                keys_to_remove.append(key)

        with open("logged_msgs.json", "w", encoding="utf-8") as f:
            json.dump(logged_msgs, f, ensure_ascii=False, indent=2)

        logger.info(f"удалено {len(keys_to_remove)} старых логов")

        if keys_to_remove:
            BOT_TOKEN = os.getenv("BOT_TOKEN")
            LOGGER_CHAT_ID = os.getenv("LOGGER_CHAT_ID")
            if BOT_TOKEN and LOGGER_CHAT_ID:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": LOGGER_CHAT_ID,
                    "text": f"удалено {len(keys_to_remove)} старых логов\nОсталось {len(logged_msgs)}",
                }
                requests.post(url, json=payload)
                logger.info("уведомление отправлено в логгер чат")

            else:
                logger.warning("не удалось отправить уведомление в логгер чат: отсутствует токен или ID")


    except Exception as e:
        logger.error(f"Ошибка при очистке: {e}")

if __name__ == "__main__":
    cleanup_task()