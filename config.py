import os
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import List

load_dotenv()


@dataclass
class Config:

    BOT_TOKEN: str = os.getenv("BOT_TOKEN")
    LOGGER_CHAT_ID: str = os.getenv("LOGGER_CHAT_ID")
    SECRET_TOKEN: str = os.getenv("WEBHOOK_SECRET", "default_secret")

    BASE_URL: str = os.getenv("BASE_URL", "https://alicerasp.alwaysdata.net/tgbot")

    DB_FILE: str = os.getenv("DB_FILE", "storage/users.db")

    COMMENTS_FILE: str = os.getenv("COMMENTS_FILE", "storage/comments.json")
    LOGGED_MSGS_FILE: str = os.getenv("LOGGED_MSGS_FILE", "storage/logged_msgs.json")

    IGNORING_CHAT_IDS: List[str] = field(default_factory=list)

    def __post_init__(self):
        ignor_chat_ids = os.getenv("IGNORING_CHAT_IDS", "")
        self.IGNORING_CHAT_IDS = [
            i.strip() for i in ignor_chat_ids.split(",") if i.strip()
        ]

    @classmethod
    @staticmethod
    def validate(cls):

        config = cls()
        required = ["BOT_TOKEN", "LOGGER_CHAT_ID"]
        missing = [var for var in required if not getattr(config, var)]
        if missing:
            raise ValueError(
                f"Отсутствуют обязательные переменные окружения: {missing}"
            )
