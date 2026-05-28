import logging
from flask import Flask, request, jsonify, render_template
from src.config import Config
from src.bot.core import TelegramBot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = Flask(__name__)


config = Config()
config.validate()


bot = TelegramBot(config)


@app.route("/tgbot/webhook", methods=["POST"])
def webhook():
    logger.info("=== ПОЛУЧЕН ВЕБХУК ОТ TELEGRAM ===")

    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_token != config.SECRET_TOKEN:
        logger.warning(f"Неавторизованный запрос. Токен: {secret_token}")
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
def webhook_status():
    """Проверка статуса вебхука"""
    import requests

    url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/getWebhookInfo"

    response = requests.get(url)
    result = response.json()
    logger.info(f"Статус вебхука: {result}")

    return jsonify(result)


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
