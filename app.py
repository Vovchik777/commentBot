from functools import wraps
import time
import datetime
import pytz  # нужно установить: pip install pytz

moscow_tz = pytz.timezone("Europe/Moscow")

from faker import Faker
from flask import Flask, request, jsonify,send_from_directory
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
    BASE   =  0
    MODER  =  1
    ADMIN  =  2
    DEV    =  3
    LOGGER =  4


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
                        return self.send_message(
                            chat_id,
                            f'недостаточно прав. минимальный уровень прав "{self.parse_permission_to_str(permission_level)}",\
                                                  ваши права "{self.parse_permission_to_str(result[0])}"',
                        )
                else:
                    return self.send_message(
                        chat_id,
                        "пользователь не найден,используйте /start или обратитесь к разработчику",
                    )
            except Exception as e:
                logger.error("ошибка при проверке прав: %s", str(e))
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
        self.help_msg = (
            f"/help - помощь - доступно от {self.parse_permission_to_str(Permissions.BASE)}\n"
            f"/get_users_list - получить список пользователей - доступно от {self.parse_permission_to_str(Permissions.BASE)}\n"
            f"/comment_list - список комментов - доступно от {self.parse_permission_to_str(Permissions.BASE)}\n"
            f"/add_comment [text | photo] [text] - доступно от {self.parse_permission_to_str(Permissions.MODER)}\n"
            f"/delete_comment [text | photo] [id] - доступно от {self.parse_permission_to_str(Permissions.MODER)}\n"
            f"/set_permission [username] [permission] - доступно от {self.parse_permission_to_str(Permissions.ADMIN)}\n"
            f"/get_user_info [chat_id | username] - доступно от {self.parse_permission_to_str(Permissions.DEV)}\n"
            f"/answer [text] - уникальная команда - доступно от {self.parse_permission_to_str(Permissions.LOGGER)}"
        )

    @staticmethod
    def parse_permission(permission):
        permission_map = {
            "base": Permissions.BASE,
            "moder": Permissions.MODER,
            "admin": Permissions.ADMIN,
            "developer": Permissions.DEV,
            "logger" : Permissions.LOGGER
        }
        return permission_map.get(permission.lower())

    def parse_permission_to_str(self, permission):
        permission_map = {
            Permissions.BASE: "базовый минимум",
            Permissions.MODER: "модер",
            Permissions.ADMIN: "админ",
            Permissions.DEV: "разработчик",
            Permissions.LOGGER : "клутой"
        }
        return permission_map.get(permission)

    def load_logged_msgs(self):
        """Загружает logged_msgs из файла, обрабатывает ошибки"""
        try:
            # Проверяем существование файла
            if not os.path.exists("logged_msgs.json"):
                self.logged_msgs = {}
                return

            with open("logged_msgs.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                # Проверяем, что данные являются словарем
                if isinstance(data, dict):
                    self.logged_msgs = data
                else:
                    logger.error(
                        "Некорректный формат данных в logged_msgs.json, ожидается словарь"
                    )
                    self.logged_msgs = {}

        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON в logged_msgs.json: {e}")
            self.logged_msgs = {}
        except Exception as e:
            logger.error(f"Ошибка загрузки logged_msgs: {e}")
            self.logged_msgs = {}

    def save_logged_msgs(self):
        """Сохраняет logged_msgs в файл, обрабатывает ошибки"""
        try:
            # Убедимся, что logged_msgs является словарем
            if not hasattr(self, "logged_msgs") or not isinstance(
                self.logged_msgs, dict
            ):
                self.logged_msgs = {}

            with open("logged_msgs.json", "w", encoding="utf-8") as f:
                json.dump(self.logged_msgs, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"Ошибка сохранения logged_msgs: {e}")

    def connect_users_db(self, db_file):
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                permission INTEGER DEFAULT 0
            )
        """
        )
        self.conn.commit()

    def get_user_permission(self, chat_id):
        result = self.cursor.execute(
            "SELECT permission FROM users WHERE chat_id = ?", (chat_id,)
        ).fetchone()

        if result and result[0] is not None:
            return result[0]
        else:
            return Permissions.BASE  # Значение по умолчанию

    def get_chat_id_by_username(self, username: str):
        if username.startswith("@"):
            username = username[1:]
        result = self.cursor.execute(
            "SELECT chat_id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if result:
            return result[0]
        else:
            logger.error(f"Пользователь с именем {username} не найден")
            raise ValueError(f"Пользователь с именем {username} не найден")

    @required_permission(Permissions.MODER)
    def set_user_pemission(self, chat_id, username_to_set_permission, permission):
        if isinstance(permission, str):
            permission = self.parse_permission(permission)

        if permission is None:
            self.send_message(chat_id, "неверный уровень доступа")
            return

        if username_to_set_permission is None:
            self.send_message(chat_id, "неверный формат команды")
            return

        chat_id_to_set_permission = self.get_chat_id_by_username(
            username_to_set_permission
        )

        if (
            chat_id_to_set_permission is None
            or not self.cursor.execute(
                "SELECT 1 FROM users WHERE username = ?", (username_to_set_permission,)
            ).fetchone()
        ):
            self.send_message(chat_id, "пользователь не найден")
            return

        if (
            self.get_user_permission(chat_id)
            > self.get_user_permission(chat_id_to_set_permission)
            and self.get_user_permission(chat_id) >= permission
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

        elif (
            self.get_user_permission(chat_id) == Permissions.DEV
            and not self.get_user_permission(chat_id_to_set_permission)
            == Permissions.DEV
        ) or str(chat_id) == str(self.logger_chat_id):
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
            self.send_message(
                chat_id, "ты чо балбес чтоль где то по условиям не сошлось"
            )

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
                self.send_message(chat_id, "Вы успешно зарегистрированы!")
                self.send_message(
                    self.logger_chat_id,
                    f"Новый пользователь: @{self.get_chat_info(chat_id).get('username')}",
                )
                return True
            else:
                logger.info(f"Пользователь уже существует: {chat_id}")
                self.send_message(chat_id, "Вы уже зарегистрированы!")
                return False

        except Exception as e:
            logger.error(f"Ошибка добавления пользователя {chat_id}: {e}")
            self.send_message(
                self.logger_chat_id, f"Ошибка добавления пользователя {chat_id}: {e}"
            )
            self.send_message(
                chat_id, "Произошла ошибка при регистрации. Попробуйте позже."
            )
            return False

    def load_comments(self):
        with open("comments.json", "r", encoding="utf-8") as f:
            comment_data = json.load(f)
            self.text_comments:list = comment_data["text"]
            self.photo_comments:list = comment_data["photo"]
            self.scheduled_comments:dict = comment_data["scheduled"]

    def save_comments(self):
        with open("comments.json", "w") as f:
            json.dump({"text": self.text_comments, "photo": self.photo_comments,"scheduled":self.scheduled_comments}, f)

    def send_message(self, chat_id, text, reply_to_message_id=None):
        """Отправка сообщения"""
        logger.info(f"Попытка отправить сообщение длиной {len(text)} символов")
        
        # Максимальная длина сообщения в Telegram
        MAX_LENGTH = 4096
        
        if len(text) <= MAX_LENGTH:
            # Обычная отправка для коротких сообщений
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
        else:
            # Разбиваем длинное сообщение на части
            logger.info(f"Сообщение слишком длинное ({len(text)} символов), разбиваем на части")
            parts = []
            current_part = ""
            
            # Разбиваем по строкам, чтобы не обрывать слова
            lines = text.split('\n')
            for line in lines:
                if len(current_part) + len(line) + 1 <= MAX_LENGTH:
                    current_part += line + '\n'
                else:
                    if current_part:
                        parts.append(current_part.strip())
                    current_part = line + '\n'
            
            if current_part:
                parts.append(current_part.strip())
            
            # Отправляем части
            results = []
            for i, part in enumerate(parts):
                logger.info(f"Отправка части {i+1}/{len(parts)} ({len(part)} символов)")
                url = f"{self.base_url}/sendMessage"
                payload = {"chat_id": chat_id, "text": part}
                
                # Только первая часть будет reply_to_message_id
                if i == 0 and reply_to_message_id:
                    payload["reply_to_message_id"] = reply_to_message_id
                
                try:
                    response = requests.post(url, json=payload)
                    results.append(response.json())
                    # Небольшая задержка между отправками
                    if i < len(parts) - 1:
                        time.sleep(0.5)
                except Exception as e:
                    logger.error(f"Ошибка отправки части {i+1}: {e}")
                    results.append(None)
            
            return results

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

    def process_message(self, message_data):
        """Обработка входящего сообщения"""
        try:
            logger.info(f"Получено сообщение: {message_data}")
            chat_id = message_data["chat"]["id"]
            chat_type = message_data["chat"]["type"]
            message_id = message_data["message_id"]
            text = message_data.get("text", "")

            logger.info(
                f"Обработка сообщения: чат {chat_id}, тип {chat_type}, текст: {text}"
            )

            # Обработка команды /start
            if text == "/start":
                return self.handle_start_command(chat_id, chat_type)

            # Обработка сообщений в группах
            elif chat_type in ["group", "supergroup"]:
                if str(chat_id) in [x for x in map(str, self.ignore_chat_ids)]:
                    return self.send_message(chat_id, "я не буду здесь работать")

                return self.handle_group_message(message_data)

            # Обработка личных сообщений
            elif chat_type == "private":
                if not str(chat_id) == str(self.logger_chat_id):
                    msg = self.send_message(
                        self.logger_chat_id,
                        f"[{datetime.datetime.now(moscow_tz).strftime('%H:%M:%S')} : @{self.get_chat_info(chat_id).get('username', 'неизвестно')} ({chat_id}), {text}]",
                    )
                    if msg:
                        for res in msg:
                            logger.info(res)
                            if res.get("ok"):
                                bot_msg_id = res.get("result").get("message_id")
                                # Сохраняем с timestamp
                                self.logged_msgs[str(bot_msg_id)] = {
                                    "chat_id": chat_id,
                                    "message_id": message_id,
                                    "timestamp": time.time(),
                                }
                                self.save_logged_msgs()

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
                if comment_text not in self.text_comments:
                    self.text_comments.append(comment_text)
                    self.send_message(
                        chat_id, f"Добавлен текстовый комментарий: {comment_text}"
                    )
                else:
                    self.send_message(chat_id, "такой комментарий уже существует")
            elif comment_type == "photo":
                if comment_text not in self.photo_comments:
                    self.photo_comments.append(comment_text)
                    self.send_message(
                        chat_id, f"Добавлен фото-комментарий: {comment_text}"
                    )
                else:
                    self.send_message(chat_id, "такой комментарий уже существует")
            else:
                self.send_message(
                    chat_id,
                    "Неверный тип комментария. Используйте /add_comment text или /add_comment photo",
                )
                return
            self.save_comments()

    @required_permission(Permissions.BASE)
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
        
        if self.get_user_permission(chat_id) == Permissions.LOGGER:
            num = 1
            for key,value in self.scheduled_comments.items():
                msg.append(f"{key}".center(15,"-"))
                for comm in self.scheduled_comments[key]:
                    msg.append(f"   {num}. {comm}")
                    num+=1
        text = "\n".join(msg)
        self.send_message(chat_id,text)

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
            elif comment_type == "schedule":
                num = 1
                for key,value in self.scheduled_comments.items():
                    if isinstance(value,list):
                        for comm in value:
                            if num == del_num:
                                del_txt = value[num-1]
                                value.pop(num-1)
                                self.scheduled_comments[key] = value
                                if not self.scheduled_comments[key]:
                                    del self.scheduled_comments[key]
                                self.save_comments()
                                self.send_message(chat_id,f"Комментарий №{del_num} ({del_txt}) ({key}) удален")
                                return
                            
                self.send_message(chat_id,"такой комментарий не найден")
                    
        else:
            self.send_message(chat_id, "Введите число")

    @required_permission(Permissions.ADMIN)
    def handle_get_user_info(self, chat_id, text):

        find_chat = text.split()[1]
        if isinstance(find_chat, str):
            try:
                find_chat = self.get_chat_id_by_username(find_chat)
            except ValueError:
                return self.send_message(chat_id, "Пользователь не найден")
        if find_chat is None:
            return self.send_message(chat_id, "Пользователь не найден")
        user_info = self.get_chat_info(find_chat)
        logger.info(find_chat, user_info, chat_id)
        self.send_message(
            self.logger_chat_id,
            f"данные по чату {find_chat}:\nID: {user_info['id']}\nИмя: {user_info.get('first_name', 'Не указано')}\nФамилия: {user_info.get('last_name', 'Не указана')}\nUsername: @{user_info.get('username', 'Не указан')}",
        )

    @required_permission(Permissions.LOGGER)
    def handle_answer(self, chat_id, text, message_data):
        # Получаем ID сообщения, на которое ответили
        reply_to_message = message_data.get("reply_to_message")
        if not reply_to_message:
            self.send_message(chat_id, "Это сообщение не является ответом на другое сообщение")
            return

        # Получаем message_id сообщения, на которое ответили
        replied_message_id = reply_to_message.get("message_id")
        if not replied_message_id:
            self.send_message(chat_id, "Не удалось определить сообщение, на которое вы ответили")
            return

        # Преобразуем в строку для поиска в JSON
        replied_message_id_str = str(replied_message_id)
        
        # НЕ перезагружаем logged_msgs, используем текущие данные в памяти
        logger.info(f"Поиск сообщения {replied_message_id_str} в logged_msgs")
        logger.info(f"Доступные ключи в logged_msgs: {list(self.logged_msgs.keys())[:10]}...")  # Первые 10 ключей
        
        # Проверяем, есть ли такой message_id в logged_msgs
        if replied_message_id_str not in self.logged_msgs:
            self.send_message(chat_id, f"Сообщение {replied_message_id_str} не найдено в логах. Всего записей: {len(self.logged_msgs)}")
            # Логируем для отладки
            logger.error(f"Сообщение {replied_message_id_str} не найдено. Доступные ключи: {list(self.logged_msgs.keys())[-10:]}")
            return

        # Получаем данные для ответа
        try:
            data = self.logged_msgs[replied_message_id_str]
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
            self.send_message(chat_id, f"Ошибка при отправке ответа: {str(e)}")

    @required_permission(Permissions.MODER)
    def handle_set_permission(self, chat_id, text):
        try:
            if len(text.split()) != 3:
                self.send_message(
                    chat_id, "Используйте: /set_permission [username] [permission]"
                )
                return
            _, username, permission = text.split()

            if username.startswith("@"):
                username = username[1:]

            if self.parse_permission(permission) is None:
                self.send_message(
                    chat_id, "Неверное значение разрешения (BASE,MODER,ADMIN)"
                )
                return
            self.set_user_pemission(chat_id, username, permission)
        except ValueError:
            self.send_message(
                chat_id, "Используйте: /set_permission [username] [permission]"
            )

    @required_permission(Permissions.BASE)
    def handle_get_users_list(self, chat_id):
        result = self.cursor.execute(
            "SELECT username,permission FROM users ORDER BY permission DESC"
        ).fetchall()
        msg = [f"Список пользователей:"]
        for i in result:
            msg.append(f"@{i[0]} - {self.parse_permission_to_str(i[1])}")
        self.send_message(chat_id, "\n".join(msg))

    @required_permission(Permissions.BASE)
    def handle_help(self, chat_id):
        self.send_message(chat_id, self.help_msg)


    @required_permission(Permissions.LOGGER)
    def handle_set_schedule_comment(self, chat_id, text):
        if len(text.split()) < 3:
            url = f"{self.base_url}/sendMessage"

            keyboard = {
                "inline_keyboard": [
                    [
                        {
                            "text": "Запланировать комментарий",
                            "web_app": {"url": f"{BASE_URL}/date_picker"},
                        }
                    ]
                ]
            }
            payload = {
                "chat_id": chat_id,
                "text" : "нажми на кнопку чтобы запланировать комментарий",
                "reply_markup" : keyboard
            }
            try:
                requests.post(url,json=payload)
                logger.info("соо с кнопкой отправлено")

            except Exception as e:
                logger.error(f"ошибка при отправке соо с кнопкой {e}")
                requests.post(url,json = {"chat_id":chat_id,"text":"ошибка при отправке сообщения"})
        else:
            date = text.split()[1]
            msg = " ".join(text.split()[2:])

            if date not in self.scheduled_comments:
                self.scheduled_comments[date] = []
            
            self.scheduled_comments[date].append(msg)

            self.save_comments()

            self.send_message(chat_id,f"комментарий ```{msg}``` добавлен на дату {date}")



    def handle_private_message(self, chat_id, text, message_id, message_data):
        """Обработка личных сообщений"""
        if text and not text.startswith("/"):
            self.send_message(
                chat_id, f"Вы написали: {text}", reply_to_message_id=message_id
            )
        elif text.startswith("/add_comment"):
            self.handle_add_comment(chat_id, text)
        elif text.startswith("/comment_list"):
            self.handle_list_comment(chat_id)
        elif text.startswith("/delete_comment"):
            self.handle_delete_comment(chat_id, text)
        elif text.startswith("/get_user_info"):
            self.handle_get_user_info(chat_id, text)
        elif text.startswith("/answer"):
            self.handle_answer(chat_id, text, message_data)
        elif text.startswith("/set_permission"):
            self.handle_set_permission(chat_id, text)
        elif text.startswith("/get_users_list"):
            self.handle_get_users_list(chat_id)
        elif text.startswith("/help"):
            self.handle_help(chat_id)
        elif text.startswith("/set_schedule_comment"):
            self.handle_set_schedule_comment(chat_id, text)

    def get_forwarded_channel_info(self, message_data):
        """Получает информацию о канале, из которого переслано сообщение"""
        try:
            sender_chat = message_data.get("sender_chat")
            if sender_chat and isinstance(sender_chat, dict):
                return sender_chat.get("title")
            
            # Если нет sender_chat, пробуем получить из chat
            chat = message_data.get("chat")
            if chat and isinstance(chat, dict):
                return chat.get("title")
            
            return None

        except Exception as e:
            logger.error(f"Ошибка получения информации о канале: {e}")
            return None

    def handle_group_message(self, message_data):
        """Обработка сообщений в группах"""
        chat_id = message_data["chat"]["id"]
        message_id = message_data["message_id"]
        text = message_data.get("text", "")
        caption = message_data.get("caption", "")

        logger.info(f"Группа '{message_data['chat'].get('title', 'Unknown')}': сообщение {message_id}")

        # Проверка на пересланные сообщения
        is_forwarded = any(key.startswith("forward") for key in message_data.keys())
        
        if is_forwarded:
            logger.info("Обнаружено пересланное сообщение!")
            return self.handle_forwarded_message(message_data)
        else:
            # Получаем информацию о пользователе
            from_user = message_data.get('from', {})
            username = from_user.get('username', 'неизвестно')
            
            channel_info = self.get_forwarded_channel_info(message_data)
            channel_text = f"СООБЩЕНИЕ ИЗ ГРУППЫ {channel_info}" if channel_info else "СООБЩЕНИЕ ИЗ ГРУППЫ"
            
            log_message = f"{channel_text}\n[{datetime.datetime.now(moscow_tz).strftime('%H:%M:%S')} : @{username} ({chat_id}), {text}]"
            
            # Отправляем сообщение в лог
            msg_result = self.send_message(self.logger_chat_id, log_message)
            
            # Исправленная обработка результата
            if msg_result:
                # Если сообщение было разбито на части, msg_result будет списком
                if isinstance(msg_result, list):
                    for result in msg_result:
                        if result and result.get("ok"):
                            bot_msg_id = result.get("result", {}).get("message_id")
                            if bot_msg_id:
                                self.logged_msgs[str(bot_msg_id)] = {
                                    "chat_id": chat_id,
                                    "message_id": message_id,
                                    "timestamp": time.time(),
                                }
                # Если одно сообщение
                elif isinstance(msg_result, dict) and msg_result.get("ok"):
                    bot_msg_id = msg_result.get("result", {}).get("message_id")
                    if bot_msg_id:
                        self.logged_msgs[str(bot_msg_id)] = {
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "timestamp": time.time(),
                        }
                
                self.save_logged_msgs()
                logger.info(f"Сообщение сохранено в лог. Всего записей: {len(self.logged_msgs)}")
            else:
                logger.error("Ошибка при отправке логов")
            
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
        chat_info = self.get_chat_info(chat_id)
        username = "неизвестно"
        
        if isinstance(chat_info, dict):
            username = chat_info.get('username', 'неизвестно')
        elif isinstance(chat_info, str):
            username = chat_info
        else:
            from_user = message_data.get('from', {})
            if isinstance(from_user, dict):
                username = from_user.get('username', 'неизвестно')
        
        channel_info = self.get_forwarded_channel_info(message_data)
        channel_text = f"СООБЩЕНИЕ ИЗ КАНАЛА {channel_info}" if channel_info else "СООБЩЕНИЕ ИЗ КАНАЛА"
        
        log_message = f"{channel_text} \n[{datetime.datetime.now(moscow_tz).strftime('%H:%M:%S')} : @{username} ({chat_id}), {caption or message_data.get('text', 'нет текста')}]"
        
        msg_result = self.send_message(self.logger_chat_id, log_message)
        
        # Обрабатываем все результаты отправки
        if msg_result:
            if isinstance(msg_result, list):
                for result in msg_result:
                    if result and result.get("ok"):
                        bot_msg_id = result.get("result", {}).get("message_id")
                        if bot_msg_id:
                            self.logged_msgs[str(bot_msg_id)] = {
                                "chat_id": chat_id,
                                "message_id": message_id,
                                "timestamp": time.time(),
                            }
            elif isinstance(msg_result, dict) and msg_result.get("ok"):
                bot_msg_id = msg_result.get("result", {}).get("message_id")
                if bot_msg_id:
                    self.logged_msgs[str(bot_msg_id)] = {
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "timestamp": time.time(),
                    }
            
            self.save_logged_msgs()
            logger.info(f"Пересланное сообщение сохранено в лог. Всего записей: {len(self.logged_msgs)}")

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

        self.check_scheduled(chat_id,message_id)

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
                logger.error(f"Ошибка получения информации о чате {chat_id}: {result}")
                return {}
        except Exception as e:
            logger.error(f"Ошибка запроса getChat для {chat_id}: {e}")
            return {}

    def check_banwords(self, chat_id, text, message_id):
        """Проверка запрещенных слов"""
        for key in banwords.keys():
            if re.search(key, text, re.IGNORECASE):
                self.send_message(
                    chat_id, banwords.get(key, "нельзя"), reply_to_message_id=message_id
                )
                return True
        return False

    def check_scheduled(self,chat_id,message_id):
        today = datetime.datetime.now(moscow_tz).strftime('%Y-%m-%d')
        logger.info(f"сегодня {today}")
        for key,value in self.scheduled_comments.items():
            logger.info(f"{today}, {key}")
            if today == key:
                for comm in self.scheduled_comments[key]:
                    self.send_message(chat_id,comm,reply_to_message_id=message_id)

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


@app.route("/tgbot/date_picker")
def date_picker():
    return send_from_directory(".","date_pick.html")


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