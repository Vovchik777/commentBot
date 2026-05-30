from functools import wraps
import logging
from flask import Flask, Response, request, jsonify, render_template
from src.config import Config
from src.bot.core import TelegramBot

from src.shared.logger import get_bot_logger

logger = get_bot_logger()


app = Flask(__name__)


config = Config()
config.validate()


bot = TelegramBot(config)

ADMIN_USER = config.ADMIN_USER
ADMIN_PASS = config.ADMIN_PASS


def require_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.authorization

        # Если учётные данные не переданы вообще → вызываем попап
        if not auth:
            return Response("Доступ защищён", 401, {"WWW-Authenticate": 'Basic realm="Admin Area"'})

        # Если учётные данные переданы, но неверны → блокируем без повторного попапа
        if auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
            return Response("Доступ запрещён: неверный логин или пароль", 403)

        return f(*args, **kwargs)

    return wrapper


@app.route("/tgbot/webhook", methods=["POST"])
def webhook():
    logger.info("=== ПОЛУЧЕН ВЕБХУК ОТ TELEGRAM ===")

    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_token != config.SECRET_TOKEN:
        logger.warning(f"Неавторизованный запрос.")
        return "Unauthorized", 401

    try:
        data = request.get_json()
        logger.info(f"Тип update: {list(data.keys())}")

        bot.process_update(data)

        return jsonify({"status": "ok"})

    except Exception as e:
        logger.error(f"Ошибка обработки вебхука: {e}", exc_info=True)
        return jsonify({"status": "error"}), 500


@app.route("/tgbot/setup", methods=["GET"])
@require_admin
def setup_webhook():
    """Установка вебхука"""
    import requests

    webhook_url = f"{config.BASE_URL}/webhook"
    url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/setWebhook"
    payload = {
        "url": webhook_url,
        "secret_token": config.SECRET_TOKEN,
        "drop_pending_updates": True,
        "allowed_updates": ["message", "edited_message"],
    }

    logger.info(f"Устанавливаем вебхук: {webhook_url}")
    response = requests.post(url, json=payload)
    result = response.json()
    logger.info(f"Результат: {result}")

    return jsonify(result)


@app.route("/tgbot/status", methods=["GET"])
@require_admin
def webhook_status():
    """Проверка статуса вебхука"""
    import requests

    url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/getWebhookInfo"

    response = requests.get(url)
    result = response.json()
    logger.info(f"Статус вебхука: {result}")

    return jsonify(result)


@app.route("/tgbot/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/tgbot/date_picker", methods=["GET"])
def date_picker():
    return render_template("date_pick.html")


@app.route("/tgbot/admin_msg", methods=["GET"])
def get_admin_msg():
    return render_template("admin_msg.html")


@app.route("/tgbot/admin_msg", methods=["POST"])
def send_admin_msg():
    try:
        data = request.get_json()
        bot.send_message(
            config.LOGGER_CHAT_ID,
            f"<b>СООБЩЕНИЕ ДЛЯ АДМИНА</b>\n\nОт {data['name']} : \n {data['message']}",
        )
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error("Ошибка при отправке сообщения админу")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/")
def index():
    return jsonify(
        {
            "status": "online",
            "service": "Telegram Bot",
            "platform": "Flask + WSGI",
            "base_url": config.BASE_URL,
        }
    )


application = app

if __name__ == "__main__":
    logger.info("Запуск Flask приложения")
    app.run(host="0.0.0.0", port=8000)
