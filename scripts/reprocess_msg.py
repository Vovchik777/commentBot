import logging
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.config import Config
from src.bot.core import TelegramBot

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def create_update_from_message(message_data, update_id=1):
    """Создает update объект из данных сообщения"""
    return {"update_id": update_id, "message": message_data}


def main():
    # Данные трех сообщений из логов
    messages_data = [
        # Первое сообщение (с подписью)
        {
            "message_id": 7558,
            "from": {"id": 777000, "is_bot": False, "first_name": "Telegram"},
            "sender_chat": {
                "id": -1002378797093,
                "title": "барабульба🏃‍♀‍➡️💥",
                "type": "channel",
            },
            "chat": {
                "id": -1002336708629,
                "title": "чат барабульба🏃‍♀‍➡️💥",
                "type": "supergroup",
            },
            "date": 1769106221,
            "forward_origin": {
                "type": "channel",
                "chat": {
                    "id": -1002378797093,
                    "title": "барабульба🏃‍♀‍➡️💥",
                    "type": "channel",
                },
                "message_id": 2923,
                "date": 1769106218,
            },
            "is_automatic_forward": True,
            "forward_from_chat": {
                "id": -1002378797093,
                "title": "барабульба🏃‍♀‍➡️💥",
                "type": "channel",
            },
            "forward_from_message_id": 2923,
            "forward_date": 1769106218,
            "media_group_id": "2386432158266827915",
            "photo": [
                {
                    "file_id": "AgACAgIAAyEFAASLR1gVAAIdhmlyay2_m3z_T7kIYk9tfppLtPPyAAL6Emsb-f-QSwK4MhOHwM_AAQADAgADcwADOAQ",
                    "file_unique_id": "AQAD-hJrG_n_kEt4",
                    "file_size": 1389,
                    "width": 67,
                    "height": 90,
                },
                {
                    "file_id": "AgACAgIAAyEFAASLR1gVAAIdhmlyay2_m3z_T7kIYk9tfppLtPPyAAL6Emsb-f-QSwK4MhOHwM_AAQADAgADbQADOAQ",
                    "file_unique_id": "AQAD-hJrG_n_kEty",
                    "file_size": 16576,
                    "width": 240,
                    "height": 320,
                },
                {
                    "file_id": "AgACAgIAAyEFAASLR1gVAAIdhmlyay2_m3z_T7kIYk9tfppLtPPyAAL6Emsb-f-QSwK4MhOHwM_AAQADAgADeAADOAQ",
                    "file_unique_id": "AQAD-hJrG_n_kEt9",
                    "file_size": 64278,
                    "width": 600,
                    "height": 800,
                },
                {
                    "file_id": "AgACAgIAAyEFAASLR1gVAAIdhmlyay2_m3z_T7kIYk9tfppLtPPyAAL6Emsb-f-QSwK4MhOHwM_AAQADAgADeQADOAQ",
                    "file_unique_id": "AQAD-hJrG_n_kEt-",
                    "file_size": 108200,
                    "width": 960,
                    "height": 1280,
                },
            ],
            "caption": "тарталетка, кстати, любит растопыривать лапки, когда греется на островке, живите с этим🤩",
            "caption_entities": [
                {
                    "offset": 87,
                    "length": 2,
                    "type": "custom_emoji",
                    "custom_emoji_id": "5422746736365968361",
                }
            ],
        },
        # Второе сообщение (без подписи, продолжение альбома)
        {
            "message_id": 7559,
            "from": {"id": 777000, "is_bot": False, "first_name": "Telegram"},
            "sender_chat": {
                "id": -1002378797093,
                "title": "барабульба🏃‍♀‍➡️💥",
                "type": "channel",
            },
            "chat": {
                "id": -1002336708629,
                "title": "чат барабульба🏃‍♀‍➡️💥",
                "type": "supergroup",
            },
            "date": 1769106221,
            "forward_origin": {
                "type": "channel",
                "chat": {
                    "id": -1002378797093,
                    "title": "барабульба🏃‍♀‍➡️💥",
                    "type": "channel",
                },
                "message_id": 2924,
                "date": 1769106218,
            },
            "is_automatic_forward": True,
            "forward_from_chat": {
                "id": -1002378797093,
                "title": "барабульба🏃‍♀‍➡️💥",
                "type": "channel",
            },
            "forward_from_message_id": 2924,
            "forward_date": 1769106218,
            "media_group_id": "2386432158266827915",
            "photo": [
                {
                    "file_id": "AgACAgIAAyEFAASLR1gVAAIdh2lyay2lxRK3rav41uNwLNT6eI4PAAL7Emsb-f-QSyB_OgsOQUlDAQADAgADcwADOAQ",
                    "file_unique_id": "AQAD-xJrG_n_kEt4",
                    "file_size": 1683,
                    "width": 90,
                    "height": 87,
                },
                {
                    "file_id": "AgACAgIAAyEFAASLR1gVAAIdh2lyay2lxRK3rav41uNwLNT6eI4PAAL7Emsb-f-QSyB_OgsOQUlDAQADAgADbQADOAQ",
                    "file_unique_id": "AQAD-xJrG_n_kEty",
                    "file_size": 22493,
                    "width": 320,
                    "height": 310,
                },
                {
                    "file_id": "AgACAgIAAyEFAASLR1gVAAIdh2lyay2lxRK3rav41uNwLNT6eI4PAAL7Emsb-f-QSyB_OgsOQUlDAQADAgADeAADOAQ",
                    "file_unique_id": "AQAD-xJrG_n_kEt9",
                    "file_size": 76072,
                    "width": 736,
                    "height": 713,
                },
            ],
        },
        # Третье сообщение (текстовое)
        {
            "message_id": 7560,
            "from": {"id": 777000, "is_bot": False, "first_name": "Telegram"},
            "sender_chat": {
                "id": -1002378797093,
                "title": "барабульба🏃‍♀‍➡️💥",
                "type": "channel",
            },
            "chat": {
                "id": -1002336708629,
                "title": "чат барабульба🏃‍♀‍➡️💥",
                "type": "supergroup",
            },
            "date": 1769106250,
            "forward_origin": {
                "type": "channel",
                "chat": {
                    "id": -1002378797093,
                    "title": "барабульба🏃‍♀‍➡️💥",
                    "type": "channel",
                },
                "message_id": 2925,
                "date": 1769106247,
            },
            "is_automatic_forward": True,
            "forward_from_chat": {
                "id": -1002378797093,
                "title": "барабульба🏃‍♀‍➡️💥",
                "type": "channel",
            },
            "forward_from_message_id": 2925,
            "forward_date": 1769106247,
            "text": "качество 4к, отвечаю😌",
            "entities": [
                {
                    "offset": 20,
                    "length": 2,
                    "type": "custom_emoji",
                    "custom_emoji_id": "5334575288321869165",
                }
            ],
        },
    ]

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
