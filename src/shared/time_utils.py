import pytz
import datetime

MOSCOW_TZ = pytz.timezone("Europe/Moscow")


def get_moscow_now() -> float:
    return datetime.datetime.now(MOSCOW_TZ).timestamp()


def get_moscow_time(format_str="%H:%M:%S") -> str:
    return datetime.datetime.now(MOSCOW_TZ).strftime(format_str)


def get_moscow_date(format_str="%Y-%m-%d") -> str:
    return datetime.datetime.now(MOSCOW_TZ).strftime(format_str)


def get_moscow_datetime_str(format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.datetime.now(MOSCOW_TZ).strftime(format_str)


__all__ = [
    "MOSCOW_TZ",
    "get_moscow_now",
    "get_moscow_time",
    "get_moscow_date",
    "get_moscow_datetime_str",
]
