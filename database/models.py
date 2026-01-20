from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class PermissionLevel(IntEnum):
    BASE = 0
    MODER = 1
    ADMIN = 2
    DEV = 3
    LOGGER = 4

    @classmethod
    def from_string(cls, value: str) -> Optional[PermissionLevel]:
        mapping = {
            "base": cls.BASE,
            "moder": cls.MODER,
            "admin": cls.ADMIN,
            "developer": cls.DEV,
            "logger": cls.LOGGER,
        }
        return mapping.get(value.lower())

    def to_string(self) -> str:
        names = {
            self.BASE: "базовый минимум",
            self.MODER: "модер",
            self.ADMIN: "админ",
            self.DEV: "разработчик",
            self.LOGGER: "очень клутой",
        }
        return names.get(self, "потом узнаем")


@dataclass
class User:
    user_id: int
    username: str
    permission: PermissionLevel = PermissionLevel.BASE
    group_id: int = None

    @property
    def table_name(self) -> str:
        return f"group_{abs(self.group_id)}"


@dataclass
class LogMessage:
    bot_message_id: int
    chat_id: int
    message_id: int
    text: str
    timestamp: float
