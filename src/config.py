import os
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import List

load_dotenv()


@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN")
    LOGGER_CHAT_ID: str = os.getenv("LOGGER_CHAT_ID")
    SECRET_TOKEN: str = os.getenv("SECRET_TOKEN")
    TG_MSG_MAX_LENGHT: int = 4096
    TG_API_REQUEST_TIMEOUT: int = 15

    BASE_URL: str = os.getenv("BASE_URL")

    DB_FILE: str = os.getenv("DB_FILE", "storage/users.db")
    DB_CONNECTION_TIMEOUT: int = 10

    IGNORING_CHAT_IDS: List[str] = field(default_factory=list)

    ADMIN_USER: str = os.getenv("ADMIN_USER", "admin")
    ADMIN_PASS: str = os.getenv("ADMIN_PASS") or os.getenv("ADMIN_PASSWORD")

    ADMIN_MSG_HEADER: str = "<b>СООБЩЕНИЕ АДМИНУ</b>\n\n"
    ADMIN_MSG_MAX_LEN: int = TG_MSG_MAX_LENGHT
    ADMIN_MSG_RATE_LIMIT: int = 3
    ADMIN_MSG_RATE_WINDOW: int = 60

    TTL_ALBUM_PROCESSED: int = 3600
    TTL_BANWORDS: int = 300

    def __post_init__(self):
        ignor_chat_ids = os.getenv("IGNORING_CHAT_IDS", "")
        self.IGNORING_CHAT_IDS = [i.strip() for i in ignor_chat_ids.split(",") if i.strip()]

    @classmethod
    # @staticmethod
    def validate(cls, scope = "web"):

        config = cls()
        required = ["BOT_TOKEN", "LOGGER_CHAT_ID"]
        if scope == "web":
            required += ["SECRET_TOKEN", "ADMIN_PASS", "BASE_URL"]
        elif scope == "cron":
            required += ["DB_FILE"]

        missing = [var for var in required if not getattr(config, var)]
        if missing:
            raise ValueError(f"Отсутствуют обязательные переменные окружения: {missing}")

        if scope == "web":
            if len(config.SECRET_TOKEN) < 16:
                raise ValueError("SECRET_TOKEN должен быть не короче 16 символов")

            if config.ADMIN_PASS == "secure_pass":
                raise ValueError("ADMIN_PASS не должен совпадать с дефолтом 'secure_pass'")
