from functools import wraps
import time
import datetime
import pytz  # нужно установить: pip install pytz

moscow_tz = pytz.timezone("Europe/Moscow")

from faker import Faker
from flask import Flask, request, jsonify
import requests
import os
import logging
import random
import re
import json
from dotenv import load_dotenv
from banwords import banwords
import threading
from enum import IntEnum
import sqlite3

load_dotenv()

app = Flask(__name__)

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
LOGGER_CHAT_ID = os.getenv("LOGGER_CHAT_ID")
SECRET_TOKEN = os.getenv("WEBHOOK_SECRET", "default_secret")
BASE_URL = "https://alicerasp.alwaysdata.net/tgbot"

# Импортируйте ваши модули

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Permissions(IntEnum):
    BASE = 0
    MODER = 1
    ADMIN = 2
    DEV = 3


def required_permission(permission_level):
    def decorator(func):
        def wrapper(self, chat_id, *args, **kwargs):
            try:
                result = self.cursor.execute(
                    f"""
                                                SELECT permission
                                                from users
                                                WHERE chat_id = ?""",
                    (chat_id,),
                )
                result = result.fetchone()

                if result:
                    logger.info(
                        "Результат: %s, Уровень прав: %s",
                        str(result[0]),
                        str(permission_level),
                    )
                    if int(result[0]) >= int(permission_level):
                        func(self, chat_id, *args, **kwargs)
                    else:
                        return self.send_message(chat_id, "недостаточно прав")
                else:
                    return self.send_message(
                        chat_id,
                        "пользователь не найден,используйте /start или обратитесь к разработчику",
                    )
            except Exception as e:

                self.send_message(
                    chat_id,
                    f"ошибка при проверке прав: {type(e).__name__}, обратитесь к разработчику",
                )

        return wrapper

    return decorator


class TelegramBot:
    def __init__(self, token, logger_chat_id, db_file):
        self.token = token
        self.logger_chat_id = logger_chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.prev_media_groups = {}  # Словарь для отслеживания media_group_id по чатам
        self.load_comments()
        self.load_logged_msgs()
        self.faker = Faker("ru_RU")
        self.faker_replace = {
            "name": lambda: self.faker.name(),
            "address": lambda: self.faker.address(),
            "phone_number": lambda: self.faker.phone_number(),
            "company": lambda: self.faker.company(),
        }
        self.prev_media_group_id = "start"
        # Добавляем блокировку для потокобезопасности
        self.lock = threading.Lock()
        # Словарь для отслеживания обработанных media_group_id
        self.processed_media_groups = {}
        self.last_cleanup = time.time()
        ignor_chat_ids = os.getenv("IGNORING_CHAT_IDS")
        self.ignore_chat_ids = [i.strip() for i in ignor_chat_ids.split(",")]
        self.connect_users_db(db_file)

    @staticmethod
    def parse_permission(permission):
        permission_map = {
            "base": Permissions.BASE,
            "moder": Permissions.MODER,
            "admin": Permissions.ADMIN,
            "developer": Permissions.DEV,
        }
        return permission_map.get(permission.lower(), Permissions.BASE)

    def parse_permission_to_str(self, permission):
        permission_map = {
            Permissions.BASE: "база",
            Permissions.MODER: "модер",
            Permissions.ADMIN: "админ",
            Permissions.DEV: "разработчик",
        }
        return permission_map.get(permission)

    def load_logged_msgs(self):
        with open("logged_msgs.json", "r") as f:
            self.logged_msgs = json.load(f)
            self.logged_msgs = {int(k): v for k, v in self.logged_msgs.items()}

    def save_logged_msgs(self):
        with open("logged_msgs.json", "w") as f:
            json.dump(self.logged_msgs, f)


    def connect_users_db(self, db_file):
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute(
            f"""CREATE TABLE IF NOT EXISTS {db_file.split(".")[0]}
                            (
                                chat_id INTEGER PRIMARY KEY,
                                username TEXT,
                                permission INTEGER
                            )"""
        )
        self.conn.commit()

    def get_user_permission(self, chat_id):
        return self.cursor.execute(
            "SELECT permission FROM users WHERE chat_id = ?", (chat_id,)
        ).fetchone()[0]

    @required_permission(Permissions.ADMIN)
    def set_user_pemission(self, chat_id, chat_id_to_set_permission, permission):
        if isinstance(permission, str):
            permission = self.parse_permission(permission)
        if self.get_user_permission(chat_id) > self.get_user_permission(
            chat_id_to_set_permission
        ):
            try:
                self.cursor.execute(
                    f"UPDATE users SET permission = ? WHERE chat_id = ?",
                    (permission, chat_id_to_set_permission),
                )
                self.conn.commit()
                self.send_message(chat_id, f"успешно")
                self.send_message(
                    chat_id_to_set_permission,
                    f"вам выдали права {self.parse_permission_to_str(permission)}",
                )
            except Exception as e:
                self.send_message(chat_id, f"ошибка {type(e).__name__}")

        else:
            self.send_message(chat_id, "ты чо балбес чтоль")

    def add_user(self, chat_id, username, permission=Permissions.BASE):
        try:
            # Если permission передан как строка, конвертируем в число
            if isinstance(permission, str):
                permission = self.parse_permission(permission)

            self.cursor.execute(
                "INSERT OR IGNORE INTO users (chat_id, username, permission) VALUES (?, ?, ?)",
                (chat_id, username, permission),
            )
            self.conn.commit()

            # Проверяем, была ли выполнена вставка
            if self.cursor.rowcount > 0:
                logger.info(f"Добавлен новый пользователь: {chat_id}, {username}")
                return True
            else:
                logger.info(f"Пользователь уже существует: {chat_id}")
                return False

        except Exception as e:
            logger.error(f"Ошибка добавления пользователя {chat_id}: {e}")
            return False

    def load_comments(self):
        with open("comments.json", "r", encoding="utf-8") as f:
            comment_data = json.load(f)
            self.text_comments = comment_data["text"]
            self.photo_comments = comment_data["photo"]

    def save_comments(self):
        with open("comments.json", "w") as f:
            json.dump({"text": self.text_comments, "photo": self.photo_comments}, f)

    def send_message(self, chat_id, text, reply_to_message_id=None):
        """Отправка сообщения"""
        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        try:
            response = requests.post(url, json=payload)
            logger.info(f"Отправлено сообщение в чат {chat_id}: {text[:50]}...")
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")
            return None

    def set_message_reaction(self, chat_id, message_id):
        """Установка реакции на сообщение"""
        url = f"{self.base_url}/setMessageReaction"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reaction": [{"type": "emoji", "emoji": "🗿"}],
        }
        try:
            response = requests.post(url, json=payload)
            logger.info(
                f"Установлена реакция на сообщение {message_id} в чате {chat_id}"
            )
            if response.status_code == 429:
                retry_after = (
                    response.json().get("parameters", {}).get("retry_after", 5)
                )
                logger.warning(
                    f"Превышено ограничение частоты. Ждем {retry_after} секунд."
                )
                time.sleep(retry_after)
                self.set_message_reaction(chat_id, message_id)
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка установки реакции: {e}")
            return None

    def cleanup_old_logs(self):
        """Очистка старых логов"""
        current_time = time.time()
        if current_time - self.last_cleanup > 3600:  # Каждый час
            # Удаляем записи старше 24 часов
            keys_to_remove = []
            for key, value in self.logged_msgs.items():
                # ИСПРАВЛЕНИЕ: получаем timestamp из value, а не через get
                if (current_time - value.get("timestamp", 0)) > 24 * 60 * 60:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self.logged_msgs[key]

            self.last_cleanup = current_time
            if keys_to_remove:
                logger.info(f"Очищено {len(keys_to_remove)} старых логов")
                self.send_message(
                    self.logger_chat_id,
                    f"Очищено {len(keys_to_remove)} старых логов",
                )
                self.save_logged_msgs()
    def process_message(self, message_data):
        """Обработка входящего сообщения"""
        try:
            chat_id = message_data["chat"]["id"]
            chat_type = message_data["chat"]["type"]
            message_id = message_data["message_id"]
            text = message_data.get("text", "")

            logger.info(
                f"Обработка сообщения: чат {chat_id}, тип {chat_type}, текст: {text}"
            )
            if str(chat_id) in [x for x in map(str, self.ignore_chat_ids)]:
                return self.send_message(chat_id, "я не буду здесь работать")

            # Обработка команды /start
            if text == "/start":
                return self.handle_start_command(chat_id, chat_type)

            # Обработка сообщений в группах
            elif chat_type in ["group", "supergroup"]:
                return self.handle_group_message(message_data)

            # Обработка личных сообщений
            elif chat_type == "private":
                msg = self.send_message(
                    self.logger_chat_id,
                    f"[{datetime.datetime.now(moscow_tz).strftime('%H:%M:%S')} : @{self.get_chat_info(chat_id).get('username', 'неизвестно')}, {text}]",
                )
                if msg and msg.get("ok"):
                    bot_msg_id = msg.get("result").get("message_id")
                    # Сохраняем с timestamp
                    self.logged_msgs[bot_msg_id] = {
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "timestamp": time.time(),
                    }
                    self.save_logged_msgs()
                    self.cleanup_old_logs()  # Периодическая очистка
                    return self.handle_private_message(
                        chat_id, text, message_id, message_data
                    )

        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")

    def handle_start_command(self, chat_id, chat_type):
        """Обработка команды /start"""
        if chat_type == "private":
            self.send_message(
                chat_id,
                "Привет! Я бот для управления комментариями. Используйте команды для добавления и удаления комментариев.",
            )
            self.add_user(chat_id, self.get_chat_info(chat_id).get("username"))

        else:
            self.send_message(
                chat_id,
                "Привет! Я бот этой группы. Я реагирую на пересланные сообщения и слежу за запрещенными словами.",
            )

    @required_permission(Permissions.MODER)
    def handle_add_comment(self, chat_id, text):

        if len(text.split()) < 3:
            self.send_message(chat_id, "Используйте /add_comment [text|photo] текст")
        else:
            comment_type = text.split()[1]
            comment_text = " ".join(text.split()[2:])
            if comment_type == "text":
                self.text_comments.append(comment_text)
                self.send_message(
                    chat_id, f"Добавлен текстовый комментарий: {comment_text}"
                )
            elif comment_type == "photo":
                self.photo_comments.append(comment_text)
                self.send_message(chat_id, f"Добавлен фото-комментарий: {comment_text}")
            else:
                self.send_message(
                    chat_id,
                    "Неверный тип комментария. Используйте /add_comment text или /add_comment photo",
                )
                return
            self.save_comments()

    def handle_list_comment(self, chat_id):
        msg = []
        num = 1
        for i in self.text_comments:
            msg.append(
                f"{num}. {i}"
                + (
                    ("( " + self.parse_comment(i, re.findall(r"{{\w+}}", i)) + " )")
                    if re.findall(r"{{\w+}}", i)
                    else ""
                )
            )
            num += 1
        msg.append("ФОТО".center(60, "="))
        num = 1
        for i in self.photo_comments:
            msg.append(
                f"{num}. {i}"
                + (
                    ("( " + self.parse_comment(i, re.findall(r"{{\w+}}", i)) + " )")
                    if re.findall(r"{{\w+}}", i)
                    else ""
                )
            )
            num += 1
        self.send_message(chat_id, "\n".join(msg))

    @required_permission(Permissions.MODER)
    def handle_delete_comment(self, chat_id, text):
        if len(text.split()) < 3:
            self.send_message(chat_id, "/delete_comment [text | photo] [номер]")
            return
        comment_type = text.split()[1]
        del_num = text.split()[2]
        if del_num.isdigit():
            del_num = int(del_num)
            if comment_type == "text":
                if del_num <= len(self.text_comments):
                    del_txt = self.text_comments[del_num - 1]
                    self.text_comments.pop(del_num - 1)
                    self.save_comments()
                    self.send_message(
                        chat_id, f"Комментарий №{del_num} ({del_txt}) удален"
                    )
                    return
                else:
                    self.send_message(
                        chat_id, "Нет такого номера. используй /comment_list"
                    )
                    return

            elif comment_type == "photo":
                if del_num <= len(self.photo_comments):
                    del_txt = self.photo_comments[del_num - 1]
                    self.photo_comments.pop(del_num - 1)
                    self.save_comments()
                    self.send_message(
                        chat_id, f"Комментарий №{del_num} ({del_txt}) удален"
                    )
                    return
                else:
                    self.send_message(
                        chat_id, "Нет такого номера. используй /comment_list"
                    )
                    return
        else:
            self.send_message(chat_id, "Введите число")

    @required_permission(Permissions.ADMIN)
    def handle_get_user_info(self, chat_id, text):
        if str(chat_id) == str(self.logger_chat_id):
            find_chat = text.split()[1]
            user_info = self.get_chat_info(find_chat)
            logger.info(find_chat, user_info, chat_id)
            self.send_message(
                self.logger_chat_id,
                f"данные по чату {find_chat}:\nID: {user_info['id']}\nИмя: {user_info.get('first_name', 'Не указано')}\nФамилия: {user_info.get('last_name', 'Не указана')}\nUsername: @{user_info.get('username', 'Не указан')}",
            )
        else:
            self.send_message(chat_id, "Недостаточно прав")

    @required_permission(Permissions.DEV)
    def handle_answer(self, chat_id, text, message_data):
        # Получаем ID сообщения, на которое ответили
        reply_to_message = message_data.get("reply_to_message")
        if not reply_to_message:
            self.send_message(
                chat_id, "Это сообщение не является ответом на другое сообщение"
            )
            return

        # Получаем message_id сообщения, на которое ответили
        replied_message_id = reply_to_message.get("message_id")
        if not replied_message_id:
            self.send_message(
                chat_id, "Не удалось определить сообщение, на которое вы ответили"
            )
            return

        # Проверяем, есть ли такой message_id в logged_msgs
        if replied_message_id not in self.logged_msgs:
            self.send_message(
                chat_id, "Сообщение, на которое вы ответили, не найдено в логах"
            )
            return

        # Получаем данные для ответа
        try:
            # ИСПРАВЛЕНИЕ: получаем данные из словаря, а не распаковываем как кортеж
            data = self.logged_msgs[replied_message_id]
            answer_chat_id = data["chat_id"]
            answer_msg_id = data["message_id"]
            answer = text.split(" ", 1)[1]  # Берем текст после "/answer "

            # Отправляем ответ
            self.send_message(answer_chat_id, answer, reply_to_message_id=answer_msg_id)
            self.send_message(chat_id, "Ответ отправлен")
        except IndexError:
            self.send_message(chat_id, "Используйте: /answer [текст ответа]")
        except Exception as e:
            logger.error(f"Ошибка отправки ответа: {e}")
            self.send_message(chat_id, "Ошибка при отправке ответа")

    def handle_private_message(self, chat_id, text, message_id, message_data):
        """Обработка личных сообщений"""
        if text and not text.startswith("/"):
            self.send_message(
                chat_id, f"Вы написали: {text}", reply_to_message_id=message_id
            )
        elif text.startwith("/add_comment"):
            self.handle_add_comment(chat_id, text)
        elif text.startwith("/list_comment"):
            self.handle_list_comment(chat_id)

        elif text.startwith("/delete_comment"):
            self.handle_delete_comment(chat_id, text)
        elif text.startwith("/get_user_info"):
            self.handle_get_user_info(chat_id, text)
        elif text.startwith("/answer") and str(chat_id) == str(self.logger_chat_id):
            self.handle_answer(chat_id, text, message_data)

    def handle_group_message(self, message_data):
        """Обработка сообщений в группах"""
        chat_id = message_data["chat"]["id"]
        message_id = message_data["message_id"]
        text = message_data.get("text", "")
        caption = message_data.get("caption", "")

        logger.info(
            f"Группа '{message_data['chat'].get('title', 'Unknown')}': сообщение {message_id}"
        )
        logger.info(f"Текст: {text}, Подпись: {caption}")
        logger.info(f"Ключи сообщения: {list(message_data.keys())}")

        # Проверка на пересланные сообщения (из каналов или других чатов)
        is_forwarded = any(key.startswith("forward") for key in message_data.keys())
        logger.info(f"Сообщение переслано: {is_forwarded}")

        if is_forwarded:
            logger.info("Обнаружено пересланное сообщение!")
            return self.handle_forwarded_message(message_data)
        else:
            # Проверка запрещенных слов в обычных сообщениях
            if text:
                return self.check_banwords(chat_id, text, message_id)

    def parse_comment(self, comment, refind):
        for i in refind:
            comment = comment.replace(
                i,
                self.faker_replace[i.replace("{{", "").replace("}}", "")](),
            )
        return comment

    def handle_forwarded_message(self, message_data):
        """Обработка пересланных сообщений"""
        logger.info("handle_forwarded_message")
        chat_id = message_data["chat"]["id"]
        message_id = message_data["message_id"]
        media_group_id = message_data.get("media_group_id")
        caption = message_data.get("caption", "")

        # Инициализация атрибута для хранения предыдущего комментария
        if not hasattr(self, "prevcomment"):
            self.prevcomment = ""

        logger.info(
            f"Обработка пересланного сообщения. media_group_id: {media_group_id}"
        )

        # Если есть media_group_id, это альбом
        if media_group_id:
            # Ждем 1.5 секунды, чтобы все сообщения из альбома успели прийти
            time.sleep(1.5)

            # Инициализация словаря для хранения типов альбомов, если его еще нет
            if not hasattr(self, "album_types"):
                self.album_types = {}

            # Определяем, является ли это сообщением с подписью
            has_caption = bool(caption)

            # Получаем текущий тип альбома (если уже определен)
            album_type = self.album_types.get(media_group_id)

            if has_caption:
                # Это альбом с подписью
                self.album_types[media_group_id] = "with_caption"
                logger.info(f"Альбом с подписью: {media_group_id}")
            elif not has_caption and not album_type:
                # Это первое сообщение альбома без подписи
                self.album_types[media_group_id] = "without_caption"
                logger.info(f"Альбом без подписи: {media_group_id}")
            elif not has_caption and album_type:
                # Это продолжение альбома - пропускаем
                logger.info("Продолжение альбома, пропускаем")
                return

            # Очищаем старые записи (старше 30 секунд)
            current_time = time.time()
            if not hasattr(self, "album_timestamps"):
                self.album_timestamps = {}

            self.album_timestamps[media_group_id] = current_time

            # Удаляем записи старше 30 секунд
            for mgid in list(self.album_types.keys()):
                if (
                    mgid not in self.album_timestamps
                    or current_time - self.album_timestamps[mgid] > 30
                ):
                    if mgid in self.album_types:
                        del self.album_types[mgid]
                    if mgid in self.album_timestamps:
                        del self.album_timestamps[mgid]

        # Установка реакции
        reaction_result = self.set_message_reaction(chat_id, message_id)
        if reaction_result and not reaction_result.get("ok"):
            logger.warning(f"Не удалось установить реакцию: {reaction_result}")

        # Выбор типа комментария
        if any(media_type in message_data for media_type in ["photo", "video"]):
            comment = random.choice(self.photo_comments)
        else:
            comment = random.choice(self.text_comments)

        # Избегаем повторения предыдущего комментария
        while comment == self.prevcomment and (
            len(self.photo_comments) > 1 or len(self.text_comments) > 1
        ):
            logger.info("идет подбор комментария")
            if any(media_type in message_data for media_type in ["photo", "video"]):
                comment = random.choice(self.photo_comments)
            else:
                comment = random.choice(self.text_comments)

        # Замена шаблонов в комментарии
        if re.findall(r"{{\w+}}", comment):
            comment = self.parse_comment(comment, re.findall(r"{{\w+}}", comment))

        # Сохраняем текущий комментарий как предыдущий
        self.prevcomment = comment

        logger.info(f"Отправка комментария: {comment}")
        self.send_message(chat_id, comment, reply_to_message_id=message_id)

    def get_chat_info(self, chat_id):
        """Получение информации о чате/пользователе по chat_id"""
        url = f"{self.base_url}/getChat"
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

    def check_banwords(self, chat_id, text, message_id):
        """Проверка запрещенных слов"""
        for key in banwords.keys():
            if re.search(key, text, re.IGNORECASE):
                self.send_message(
                    chat_id, banwords.get(key, "нельзя"), reply_to_message_id=message_id
                )
                return True
        return False


# Инициализация бота
bot = TelegramBot(BOT_TOKEN, LOGGER_CHAT_ID, "users.db")


@app.route("/tgbot/webhook", methods=["POST"])
def webhook():
    """Обработчик вебхука от Telegram"""
    logger.info("=== ПОЛУЧЕН ВЕБХУК ОТ TELEGRAM ===")

    # Проверка секретного токена
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_token != SECRET_TOKEN:
        logger.warning(f"Неавторизованный запрос. Токен: {secret_token}")
        return "Unauthorized", 401

    try:
        data = request.get_json()
        logger.info(f"Тип update: {list(data.keys())}")

        # Обработка сообщения
        if "message" in data:
            bot.process_message(data["message"])
        elif "edited_message" in data:
            logger.info("Получено редактированное сообщение")
        else:
            logger.info(f"Получен update другого типа: {list(data.keys())}")

        return jsonify({"status": "ok"})

    except Exception as e:
        logger.error(f"Ошибка обработки вебхука: {e}", exc_info=True)
        return jsonify({"status": "error"}), 500


@app.route("/tgbot/setup", methods=["GET"])
def setup_webhook():
    """Установка вебхука"""
    webhook_url = f"{BASE_URL}/webhook"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    payload = {
        "url": webhook_url,
        "secret_token": SECRET_TOKEN,
        "drop_pending_updates": True,
        "allowed_updates": ["message", "edited_message"],
    }

    logger.info(f"Устанавливаем вебхук: {webhook_url}")
    response = requests.post(url, json=payload)
    result = response.json()
    logger.info(f"Результат: {result}")

    return jsonify(result)


@app.route("/tgbot/remove", methods=["GET"])
def remove_webhook():
    """Удаление вебхука"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"

    logger.info("Удаляем вебхук")
    response = requests.post(url)
    result = response.json()
    logger.info(f"Результат: {result}")

    return jsonify(result)


@app.route("/tgbot/status", methods=["GET"])
def webhook_status():
    """Проверка статуса вебхука"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"

    response = requests.get(url)
    result = response.json()
    logger.info(f"Статус вебхука: {result}")

    return jsonify(result)


@app.route("/tgbot/test", methods=["GET"])
def test():
    """Тестовый маршрут"""
    return jsonify(
        {
            "status": "ok",
            "message": "Бот работает!",
            "features": [
                "Реагирует на команду /start",
                "Отвечает на пересланные сообщения из каналов",
                "Ставит реакции 🗿 на пересланные сообщения",
                "Проверяет запрещенные слова",
                "Отвечает в личных сообщениях",
            ],
        }
    )


@app.route("/")
def index():
    return jsonify(
        {
            "status": "online",
            "service": "Telegram Bot",
            "platform": "Flask + WSGI",
            "base_url": BASE_URL,
        }
    )


# WSGI application
application = app

if __name__ == "__main__":
    logger.info("Запуск Flask приложения")
    app.run(host="0.0.0.0", port=8000)
