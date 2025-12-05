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

        # ИЗМЕНЕНИЕ: Правильный формат данных для истории
        cleanup_record = {
            "timestamp": datetime.datetime.now(moscow_tz).strftime("%Y-%m-%d %H:%M:%S"),
            "date_display": datetime.datetime.now(moscow_tz).strftime("%d.%m %H:%M"),
            "total": len(keys_to_remove),
            "logs": []
        }

        for key in keys_to_remove:
            log_entry = {
                "message_id": logged_msgs[key]["message_id"],
                "chat_id": logged_msgs[key]["chat_id"],
                "text": logged_msgs[key]["text"][:100] + "..." if len(logged_msgs[key]["text"]) > 100 else logged_msgs[key]["text"],
                "original_timestamp": datetime.datetime.fromtimestamp(logged_msgs[key]["timestamp"]).strftime("%d.%m %H:%M")
            }
            cleanup_record["logs"].append(log_entry)
            del logged_msgs[key]

        with open("logged_msgs.json", "w", encoding="utf-8") as f:
            json.dump(logged_msgs, f, ensure_ascii=False, indent=2)

        logger.info(f"удалено {len(keys_to_remove)} старых логов")

        if keys_to_remove:
            BOT_TOKEN = os.getenv("BOT_TOKEN")
            LOGGER_CHAT_ID = os.getenv("LOGGER_CHAT_ID")
            if BOT_TOKEN and LOGGER_CHAT_ID:
                keyboard = {
                    "inline_keyboard": [
                        [
                            {
                                "text": "просмотреть историю",
                                "web_app": {
                                    "url": "https://alicerasp.alwaysdata.net/tgbot/deleted_logs"
                                },
                            }
                        ]
                    ]
                }
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": LOGGER_CHAT_ID,
                    "text": f"удалено {len(keys_to_remove)} старых логов",
                    "reply_markup": keyboard,
                }
                requests.post(url, json=payload)
                logger.info("уведомление отправлено в логгер чат")

            else:
                logger.warning("не удалось отправить уведомление в логгер чат: отсутствует токен или ID")

            try:
                response = requests.post(
                    "https://alicerasp.alwaysdata.net/tgbot/deleted_logs", 
                    json=cleanup_record
                )
                if response.status_code == 200:
                    logger.info(f"отправлено {len(keys_to_remove)} удаленных логов на сервер")
                else:
                    logger.warning(f"ошибка отправки на сервер {response.status_code}")

            except requests.exceptions.RequestException as e:
                logger.error(f"ошибка при отправке данных на сервер: {e}")

    except Exception as e:
        logger.error(f"Ошибка при очистке: {e}")

if __name__ == "__main__":
    cleanup_task()