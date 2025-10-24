from flask import Flask, request, jsonify
import requests
import os
import logging
import random
import re
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
SECRET_TOKEN = os.getenv("WEBHOOK_SECRET", "default_secret")
BASE_URL = "https://alicerasp.alwaysdata.net/tgbot"

# Импортируйте ваши модули
try:
    from comments import comments, ph_comments
    from banwords import banwords
except ImportError:
    # Заглушки если файлы не найдены
    comments = ["Отличный пост!", "Интересно!"]
    ph_comments = ["Классное фото!"]
    banwords = {"спам": "Не спамьте!"}

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, token):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.prev_media_groups = {}  # Словарь для отслеживания media_group_id по чатам

    def send_message(self, chat_id, text, reply_to_message_id=None):
        """Отправка сообщения"""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text
        }
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
            "reaction": [{"type": "emoji", "emoji": "🗿"}]
        }
        try:
            response = requests.post(url, json=payload)
            logger.info(f"Установлена реакция на сообщение {message_id} в чате {chat_id}")
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка установки реакции: {e}")
            return None

    def process_message(self, message_data):
        """Обработка входящего сообщения"""
        try:
            chat_id = message_data['chat']['id']
            chat_type = message_data['chat']['type']
            message_id = message_data['message_id']
            text = message_data.get('text', '')
            
            logger.info(f"Обработка сообщения: чат {chat_id}, тип {chat_type}, текст: {text}")

            # Обработка команды /start
            if text == '/start':
                return self.handle_start_command(chat_id, chat_type)
            
            # Обработка сообщений в группах
            elif chat_type in ['group', 'supergroup']:
                return self.handle_group_message(message_data)
                
            # Обработка личных сообщений
            elif chat_type == 'private':
                return self.handle_private_message(chat_id, text, message_id)
                
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")

    def handle_start_command(self, chat_id, chat_type):
        """Обработка команды /start"""
        if chat_type == 'private':
            msg = []
            for c in comments:
                if callable(c):
                    comm = c()
                else:
                    comm = c
                msg.append("-- " + comm)
            msg.append("PHOTO".center(60, "="))
            for c in ph_comments:
                if callable(c):
                    comm = c()
                else:
                    comm = c
                msg.append("-- " + comm)
            self.send_message(chat_id, "\n".join(msg))
        else:
            self.send_message(chat_id, "Привет! Я бот этой группы. Я реагирую на пересланные сообщения и слежу за запрещенными словами.")

    def handle_private_message(self, chat_id, text, message_id):
        """Обработка личных сообщений"""
        if text and not text.startswith('/'):
            self.send_message(chat_id, f"Вы написали: {text}", reply_to_message_id=message_id)

    def handle_group_message(self, message_data):
        """Обработка сообщений в группах"""
        chat_id = message_data['chat']['id']
        message_id = message_data['message_id']
        text = message_data.get('text', '')
        caption = message_data.get('caption', '')
        
        logger.info(f"Группа '{message_data['chat'].get('title', 'Unknown')}': сообщение {message_id}")
        logger.info(f"Текст: {text}, Подпись: {caption}")
        logger.info(f"Ключи сообщения: {list(message_data.keys())}")
        
        # Проверка на пересланные сообщения (из каналов или других чатов)
        is_forwarded = any(key.startswith('forward') for key in message_data.keys())
        logger.info(f"Сообщение переслано: {is_forwarded}")
        
        if is_forwarded:
            logger.info("Обнаружено пересланное сообщение!")
            return self.handle_forwarded_message(message_data)
        else:
            # Проверка запрещенных слов в обычных сообщениях
            if text:
                return self.check_banwords(chat_id, text, message_id)

    def handle_forwarded_message(self, message_data):
        """Обработка пересланных сообщений"""
        chat_id = message_data['chat']['id']
        message_id = message_data['message_id']
        media_group_id = message_data.get('media_group_id')
        caption = message_data.get('caption', '')
        
        logger.info(f"Обработка пересланного сообщения. media_group_id: {media_group_id}")
        
        # Инициализация для чата, если нужно
        if chat_id not in self.prev_media_groups:
            self.prev_media_groups[chat_id] = None
        
        # Проверяем, не обрабатывали ли мы уже этот media_group
        if media_group_id and media_group_id == self.prev_media_groups[chat_id]:
            logger.info(f"Пропускаем дубликат media_group: {media_group_id}")
            return
            
        # Обновляем последний обработанный media_group_id
        if media_group_id:
            self.prev_media_groups[chat_id] = media_group_id
        
        # Установка реакции
        reaction_result = self.set_message_reaction(chat_id, message_id)
        if reaction_result and not reaction_result.get('ok'):
            logger.warning(f"Не удалось установить реакцию: {reaction_result}")
        
        # Отправка комментария
        if any(media_type in message_data for media_type in ['photo', 'video', 'document', 'audio']):
            comment = random.choice(ph_comments)
        else:
            comment = random.choice(comments)
        
        if callable(comment):
            comm = comment()
        else:
            comm = comment
            
        self.send_message(chat_id, comm, reply_to_message_id=message_id)

    def check_banwords(self, chat_id, text, message_id):
        """Проверка запрещенных слов"""
        for key in banwords.keys():
            if re.search(key, text, re.IGNORECASE):
                self.send_message(chat_id, banwords.get(key, "нельзя"), reply_to_message_id=message_id)
                return True
        return False

# Инициализация бота
bot = TelegramBot(BOT_TOKEN)

@app.route('/tgbot/webhook', methods=['POST'])
def webhook():
    """Обработчик вебхука от Telegram"""
    logger.info("=== ПОЛУЧЕН ВЕБХУК ОТ TELEGRAM ===")
    
    # Проверка секретного токена
    secret_token = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    if secret_token != SECRET_TOKEN:
        logger.warning(f"Неавторизованный запрос. Токен: {secret_token}")
        return "Unauthorized", 401
    
    try:
        data = request.get_json()
        logger.info(f"Тип update: {list(data.keys())}")
        
        # Обработка сообщения
        if 'message' in data:
            bot.process_message(data['message'])
        elif 'edited_message' in data:
            logger.info("Получено редактированное сообщение")
        else:
            logger.info(f"Получен update другого типа: {list(data.keys())}")
        
        return jsonify({"status": "ok"})
    
    except Exception as e:
        logger.error(f"Ошибка обработки вебхука: {e}", exc_info=True)
        return jsonify({"status": "error"}), 500

@app.route('/tgbot/setup', methods=['GET'])
def setup_webhook():
    """Установка вебхука"""
    webhook_url = f"{BASE_URL}/webhook"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    payload = {
        "url": webhook_url,
        "secret_token": SECRET_TOKEN,
        "drop_pending_updates": True,
        "allowed_updates": ["message", "edited_message"]
    }
    
    logger.info(f"Устанавливаем вебхук: {webhook_url}")
    response = requests.post(url, json=payload)
    result = response.json()
    logger.info(f"Результат: {result}")
    
    return jsonify(result)

@app.route('/tgbot/remove', methods=['GET'])
def remove_webhook():
    """Удаление вебхука"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
    
    logger.info("Удаляем вебхук")
    response = requests.post(url)
    result = response.json()
    logger.info(f"Результат: {result}")
    
    return jsonify(result)

@app.route('/tgbot/status', methods=['GET'])
def webhook_status():
    """Проверка статуса вебхука"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
    
    response = requests.get(url)
    result = response.json()
    logger.info(f"Статус вебхука: {result}")
    
    return jsonify(result)

@app.route('/tgbot/test', methods=['GET'])
def test():
    """Тестовый маршрут"""
    return jsonify({
        "status": "ok", 
        "message": "Бот работает!",
        "features": [
            "Реагирует на команду /start",
            "Отвечает на пересланные сообщения из каналов",
            "Ставит реакции 🗿 на пересланные сообщения",
            "Проверяет запрещенные слова",
            "Отвечает в личных сообщениях"
        ]
    })

@app.route('/')
def index():
    return jsonify({
        "status": "online",
        "service": "Telegram Bot",
        "platform": "Flask + WSGI",
        "base_url": BASE_URL
    })

# WSGI application
application = app

if __name__ == '__main__':
    logger.info("Запуск Flask приложения")
    app.run(host='0.0.0.0', port=8000)