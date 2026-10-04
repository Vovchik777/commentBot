from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum
from typing import Optional

from src.shared.time_utils import get_moscow_date


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
            "dev": cls.DEV,
            "logger": cls.LOGGER,
        }
        return mapping.get(value.lower().strip())

    def to_string(self) -> str:
        names = {
            self.BASE: "базовый минимум",
            self.MODER: "модер",
            self.ADMIN: "админ",
            self.DEV: "разработчик",
            self.LOGGER: "очень клутой",
        }
        return names.get(self, "потом узнаем")


class CommentTypes(str, Enum):
    TEXT = "text"
    PHOTO = "photo"
    SCHEDULED = "scheduled"

    @classmethod
    def from_str(cls, value: str) -> "CommentTypes | None":
        if not isinstance(value, str):
            return None
        try:
            return cls(value.lower().strip())
        except ValueError:
            return None


@dataclass
class User:
    tg_group_id: int
    tg_user_id: int
    username: str
    permission: PermissionLevel = PermissionLevel.BASE

    # @property
    # def table_name(self) -> str:
    #     return f"group_{abs(self.group_id)}"


@dataclass
class LogMessage:
    bot_message_id: int
    chat_id: int
    message_id: int
    text: str
    timestamp: float


@dataclass
class Comment:
    group_id: int
    comment_type: CommentTypes
    comment_text: str
    scheduled_date: Optional[str] = None
    use_count: int = 0

    def __post_init__(self):
        if isinstance(self.comment_type, CommentTypes):
            return
        parsed = CommentTypes.from_str(self.comment_type)
        if parsed is None:
            raise ValueError(f"Неизвестный тип комментария: {self.comment_type!r}")
        self.comment_type = parsed

    @staticmethod
    def parse_scheduled_date(raw: str) -> Optional[str]:
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            return None
        if parsed.strftime("%Y-%m-%d") != raw:
            return None
        if raw < get_moscow_date():
            return None
        return raw
    
@dataclass
class Banword:
    group_id: int
    pattern: str
    reply: str
