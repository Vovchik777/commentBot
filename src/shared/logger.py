import logging
import os
from logging.handlers import TimedRotatingFileHandler


class SingleLineFilter(logging.Filter):
    def filter(self, record):
        if record.msg and isinstance(record.msg, str):
            record.msg = record.msg.replace("\n", " | ").replace("\r", " ").replace("\t", " ")
        return True


def _init_logger(
    name: str,
    log_file: str,
    level=logging.INFO,
) -> logging.Logger:
    log_path = os.path.abspath(log_file)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_h = TimedRotatingFileHandler(log_path, when="midnight", interval=1, backupCount=7, encoding="utf-8")
    file_h.setFormatter(fmt)
    file_h.addFilter(SingleLineFilter())
    logger.addHandler(file_h)

    logger.info(f"✅ Логгер '{name}' запущен. Файл: {log_path}")
    return logger


def get_bot_logger() -> logging.Logger:
    return _init_logger("commentBot.bot", "logs/bot.log")


def get_cron_logger() -> logging.Logger:
    return _init_logger("commentBot.cron", "logs/cron.log")
