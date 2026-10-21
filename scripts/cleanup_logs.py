
import pytz
import requests

moscow_tz = pytz.timezone("Europe/Moscow")
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.config import Config
from src.bot.services.message_logging import MessageLogsManager
from src.shared.logger import get_cron_logger

logger = get_cron_logger()
# sys.path.append(os.path.dirname(os.path.abspath(__file__)))

cfg = Config()
cfg.validate(scope="cron")


def cleanup_task():
    try:

        keys_to_remove = MessageLogsManager(cfg.DB_FILE).cleanup_old_logs()
        logged_msgs = MessageLogsManager(cfg.DB_FILE).get_logged_messages()

        if keys_to_remove == -1:
            logger.error("keys_to_remove == -1")
            return

        logger.info(f"удалено {keys_to_remove} старых логов")
        logger.info(f"{logged_msgs}")
        logger.info(f"осталось {len(logged_msgs)}")

        if keys_to_remove:
            BOT_TOKEN = cfg.BOT_TOKEN
            LOGGER_CHAT_ID = cfg.LOGGER_CHAT_ID
            if BOT_TOKEN and LOGGER_CHAT_ID:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": LOGGER_CHAT_ID,
                    "text": f"удалено {keys_to_remove} старых логов\nОсталось {len(logged_msgs)}",
                }
                try:
                        response = requests.post(url, json=payload, timeout=cfg.TG_API_REQUEST_TIMEOUT)
                        response.raise_for_status()
                        logger.info("уведомление отправлено в логгер чат")
                        
                
                except requests.exceptions.Timeout:
                    logger.error("Таймаут запроса к апи тг")
                except Exception as e:
                    logger.error(f"ошибка при запросе к апи тг {e}")

            else:
                logger.warning("не удалось отправить уведомление в логгер чат: отсутствует токен или ID")

    except Exception as e:
        logger.error(f"Ошибка при очистке: {e}")


if __name__ == "__main__":
    cleanup_task()
