import hmac
import time
from flask import Flask, request, jsonify, render_template, g
from src.config import Config
from src.bot.core import TelegramBot
from src.web.auth import require_admin
from src.web.admin import admin
from src.shared.logger import get_bot_logger, get_requests_logger

logger = get_bot_logger()
request_logger = get_requests_logger()


app = Flask(__name__, template_folder="web/templates")

config = Config()
config.validate()
app.extensions["config"] = config

app.register_blueprint(admin)


bot = TelegramBot(config)
app.extensions["bot"] = bot

@app.before_request
def _start_timer():
    g.start_time = time.time()

@app.after_request
def _log_request(response):
    if request.path == '/favicon.ico':
        return response

    now = time.time()
    duration = round((now - g.get('start_time', now)) * 1000, 2)
    endpoint = request.endpoint or "unknown"

    log_message = f"[{request.remote_addr}] {request.method:<4} | {response.status_code} | {duration:>7}ms | {endpoint:<15} | {request.full_path.rstrip('?')}"
    if response.status_code >= 500:
        log_cmd = request_logger.error
    elif duration > 7 * 1000:
        log_cmd = request_logger.warning
    else: 
        log_cmd = request_logger.info


    if log_cmd : log_cmd(log_message)

    return response


    


@app.route("/tgbot/webhook", methods=["POST"])
def webhook():
    logger.info("=== ПОЛУЧЕН ВЕБХУК ОТ TELEGRAM ===")

    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not hmac.compare_digest(
        (secret_token or "").encode(),
        (config.SECRET_TOKEN or "").encode(),
    ):
        logger.warning("Неавторизованный запрос.")
        return "Unauthorized", 401

    try:
        data = request.get_json()
        logger.info(f"Тип update: {list(data.keys())}")

        bot.process_update(data)

        return jsonify({"status": "ok"})

    except Exception as e:
        logger.error(f"Ошибка обработки вебхука: {e}", exc_info=True)
        return jsonify({"status": "error"}), 500


@app.route("/tgbot/setup", methods=["POST"])
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

    try:
        logger.info(f"Устанавливаем вебхук: {webhook_url}")

        response = requests.post(url, json=payload, timeout=config.TG_API_REQUEST_TIMEOUT)
        response.raise_for_status()
        result = response.json()
        logger.info(f"Результат: {result}")

        return jsonify(result)

    except requests.exceptions.Timeout:
        logger.error("Таймаут запроса к апи тг")
        return jsonify(
            {
                "ok": False,
                "error_code": 504,
                "description": f"Gateway Timeout: Telegram API didn`t respond at {config.TG_API_REQUEST_TIMEOUT} sec",
            }
        )

    except Exception as e:
        logger.error(f"ошибка при запросе к апи тг {e}")

        if getattr(e, "response", None) is not None:
            try:
                return jsonify(e.response.json()), e.response.status_code
            except ValueError:
                pass

        return jsonify(
            {"ok": False, "error_code": 502, "description": f"Bad Gateway: {str(e)}"}
        ), 502


@app.route("/tgbot/status", methods=["GET"])
@require_admin
def webhook_status():
    """Проверка статуса вебхука"""
    import requests

    url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/getWebhookInfo"

    response = requests.get(url, timeout=config.TG_API_REQUEST_TIMEOUT)
    response.raise_for_status()
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
    ip = request.headers.get("X-Forwarded-For") or request.remote_addr
    if bot.db.admin_msg_rate_hit(ip):
        logger.warning(f"Rate limit для admin_msg с {ip}")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": (
                        "Вы отправили слишком много сообщений. "
                        "Пожалуйста, немного подождите и попробуйте снова."
                    ),
                }
            ),
            429,
        )

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}

    # honeypot: поле скрыто от людей, боты его заполняют — молча игнорируем
    if str(data.get("website", "")).strip():
        return jsonify({"status": "ok"})

    message = str(data.get("message", "")).strip()
    if not message:
        return jsonify(
            {"status": "error", "message": "Пожалуйста, напишите сообщение перед отправкой."}
        ), 400

    result = bot.send_message(
        config.LOGGER_CHAT_ID,
        config.ADMIN_MSG_HEADER + "{message}",
        escape={"message": message},
    )

    if not (result or {}).get("ok"):
        if isinstance(result, dict) and result.get("error") == "too_long":
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": (
                            "Сообщение получилось слишком длинным. "
                            "Пожалуйста, сократите его и отправьте снова."
                        ),
                    }
                ),
                400,
            )
        logger.error(f"Ошибка при отправке сообщения админу: {result}")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Не удалось отправить сообщение. Пожалуйста, попробуйте ещё раз чуть позже.",
                }
            ),
            500,
        )

    return jsonify({"status": "ok"})


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
