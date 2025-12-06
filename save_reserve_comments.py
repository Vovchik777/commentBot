import json
import os
import logging
import dotenv
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dotenv.load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
LOGGER_CHAT_ID = os.getenv("LOGGER_CHAT_ID")


def save_reserve_comments():
    try:
        with open("comments.json", "r", encoding="utf-8") as f:
            comments = json.load(f)
    except FileNotFoundError:
        logger.warning("файл comments.json не найден")
        return
    
    with open("reserve_comments.json", "w", encoding="utf-8") as f:
        json.dump(comments, f, ensure_ascii=False, indent=2)
    logger.info("резервная копия комментариев сохранена")
    if BOT_TOKEN and LOGGER_CHAT_ID:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": LOGGER_CHAT_ID,
            "text": f"резервная копия комментариев сохранена",
        }
        requests.post(url, json=payload)


if __name__ == "__main__":
    save_reserve_comments()
else:
    logger.info(f"модуль загружен")
