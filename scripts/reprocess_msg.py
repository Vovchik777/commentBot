import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.config import Config
from src.bot.core import TelegramBot

from src.shared.logger import get_cron_logger

logger = get_cron_logger()


def create_update_from_message(message_data, update_id=1):
    """Создает update объект из данных сообщения"""
    return {"update_id": update_id, "message": message_data}


def main():
    # Данные трех сообщений из логов
    messages_data = []

    try:
        # Инициализация бота
        config = Config()
        config.validate()
        bot = TelegramBot(config)

        logger.info("Начинаю повторную обработку 3 сообщений...")

        # Обрабатываем каждое сообщение
        for i, message_data in enumerate(messages_data, 1):
            logger.info(f"Обработка сообщения {i}/3 (ID: {message_data['message_id']})...")

            # Создаем update объект
            update = create_update_from_message(message_data, update_id=1000000 + i)

            # Передаем на обработку
            bot.process_update(update)

            # Небольшая пауза между сообщениями
            import time

            time.sleep(0.5)

        logger.info("Все сообщения успешно обработаны!")

    except Exception as e:
        logger.error(f"Ошибка при повторной обработке: {e}", exc_info=True)


if __name__ == "__main__":
    main()
