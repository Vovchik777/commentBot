import sqlite3
from os import getenv,path
from dotenv import load_dotenv
import sys
import requests
import logging

sys.path.append(path.dirname(path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = getenv("BOT_TOKEN")
LOGGER_CHAT_ID = getenv("LOGGER_CHAT_ID")
base_url = f"https://api.telegram.org/bot{BOT_TOKEN}"


def get_chat_info(chat_id):
    url = f"{base_url}/getChat"
    payload = {"chat_id": chat_id}

    try:
        response = requests.post(url, json=payload)
        result = response.json()

        if result.get("ok"):
            return result.get("result")
        else:
            logger.error(f"Ошибка получения информации о чате: {result}")
            return None
    except Exception as e:
        logger.error(f"Ошибка запроса getChat: {e}")
        return None

def update():
    conn = sqlite3.connect("users.db")

    cursor = conn.cursor()

    users = cursor.execute("SELECT chat_id, username FROM users").fetchall()

    for user in users:
        try:
            chat_id, username = user
            current_username = get_chat_info(chat_id).get("username")
            if current_username:
                if current_username != username:
                    cursor.execute(
                        "UPDATE users SET username = ? WHERE chat_id = ?",
                        (current_username, chat_id),
                    )
                    conn.commit()
                    logging.info(
                        f"Обновлен пользователь @{username} на @{current_username}, {chat_id=}"
                    )
                    payload = {
                        "chat_id": LOGGER_CHAT_ID,
                        "text": f"Обновлен пользователь {username} на {current_username}, {chat_id=}"
                    }
                    requests.post(f"{base_url}/sendMessage",json=payload)
        except Exception as e:
            logging.error("ошибка при обновлении пользователя")
        
if __name__ == "__main__":
    update()
    logger.info("обновление закончилось")