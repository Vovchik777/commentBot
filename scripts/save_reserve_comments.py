import json
import os
import logging
import dotenv
import requests
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dotenv.load_dotenv()

cfg = Config()
cfg.validate()

BOT_TOKEN = cfg.BOT_TOKEN
LOGGER_CHAT_ID = cfg.LOGGER_CHAT_ID

RESERVE_COMMENTS_FILE = os.path.dirname(cfg.COMMENTS_FILE) + "/reserve_comments.json"


def save_reserve_comments():
    try:
        with open(cfg.COMMENTS_FILE, "r", encoding="utf-8") as f:
            comments = json.load(f)
    except FileNotFoundError:
        logger.warning(f"файл {cfg.COMMENTS_FILE} не найден")
        return

    with open(RESERVE_COMMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(comments, f, ensure_ascii=False, indent=2)
    logger.info("резервная копия комментариев сохранена")
    if BOT_TOKEN and LOGGER_CHAT_ID:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": LOGGER_CHAT_ID,
            "text": "резервная копия комментариев сохранена",
        }
        requests.post(url, json=payload)


if __name__ == "__main__":
    save_reserve_comments()
else:
    logger.info("модуль загружен")
