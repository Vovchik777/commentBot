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


def get_user_info(user_id):
    url = f"{base_url}/getChat"
    payload = {"chat_id": user_id}

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

def update(db_path = "users.db"):
    conn = sqlite3.connect(db_path)

    cursor = conn.cursor()

    cursor.execute("SELECT name from sqlite_master WHERE type='table' AND name LIKE 'group_%'")
    tables = [row[0] for row in cursor.fetchall()]
    # Инициализация users перед циклом
    users = [] 
    for table in tables:
        cursor.execute(f"SELECT user_id, username FROM {table}")
        for user_id, username in cursor.fetchall():
            users.append((table, user_id, username))
        print(users)
    # print(users)

    for user in users:
        try:
            table, user_id, username = user
            current_username = get_user_info(user_id).get("username")
            if current_username:
                if current_username != username:
                    cursor.execute(
                        f"UPDATE {table} SET username = ? WHERE user_id = ?",
                        (current_username, user_id),
                    )
                    conn.commit()
                    logging.info(
                        f"Обновлен пользователь @{username} на @{current_username}, {user_id=}"
                    )
                    payload = {
                        "chat_id": LOGGER_CHAT_ID,
                        "text": f"Обновлен пользователь {username} на {current_username}, {user_id=}"
                    }
                    requests.post(f"{base_url}/sendMessage",json=payload)
        except Exception as e:
            logging.error("ошибка при обновлении пользователя", e)
        
if __name__ == "__main__":
    update('users.db')
    logger.info("обновление закончилось")