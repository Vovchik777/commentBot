import re
import time
from typing import Optional, Dict, Any, List, Set, Tuple

from faker import Faker

from src.config import Config
from src.database.models import Banword, Comment, CommentTypes
from src.database.repository import DataBaseManager
from src.shared.logger import get_db_logger

logger = get_db_logger()
config = Config()


class CommentsManager:
    def __init__(self, db: DataBaseManager):
        self.db = db
        self.faker = Faker("ru_RU")
        self.faker_replace = {
            "name": lambda: self.faker.name(),
            "address": lambda: self.faker.address(),
            "phone_number": lambda: self.faker.phone_number(),
            "company": lambda: self.faker.company(),
        }
        self._bad_patterns: Set[str] = set()
        self._last_comments: Dict[int, str] = {}
        self._banwords_ram: Dict[int, Tuple[float, List[Banword]]] = {}

    def init_group_comments(self, group_id: int) -> None:
        logger.info(f"Группа {group_id} готова к работе с комментариями (SQLite)")

    def add_comment(self, comment: Comment) -> bool:
        return self.db.add_comment(comment)

    def delete_comment(self, group_id: int, comment_type: CommentTypes, index: int) -> Optional[Comment]:
        return self.db.delete_comment(group_id, comment_type, index)

    def get_random_comment(self, group_id: int, comment_type: CommentTypes) -> Optional[Comment]:
        return self.db.get_random_comment(group_id, comment_type)

    def get_scheduled_for_today(self, group_id: int, today_str: str) -> List[Comment]:
        return self.db.get_scheduled_for_today(group_id, today_str)

    def get_comments_list(self, group_id: int) -> Dict[str, Any]:
        return self.db.get_comments_list(group_id)

    def get_last_comment(self, chat_id: int) -> Optional[str]:
        cached = self._last_comments.get(chat_id)
        if cached is not None:
            return cached

        stored = self.db.get_last_comment(chat_id)
        if stored is not None:
            self._last_comments[chat_id] = stored
        return stored

    def set_last_comment(self, chat_id: int, text: str) -> None:
        self._last_comments[chat_id] = text
        self.db.set_last_comment(chat_id, text)

    def get_banwords_list(self, group_id: int) -> List[Banword]:
        return self.db.get_banwords_list(group_id)

    def _get_banwords_cached(self, group_id: int) -> List[Banword]:
        now = time.time()
        ram = self._banwords_ram.get(group_id)
        if ram is not None and ram[0] > now:
            return ram[1]

        cached = self.db.get_banwords_cache(group_id)
        if cached is not None:
            banwords, expires_at = cached
        else:
            banwords = self.get_banwords_list(group_id)
            expires_at = self.db.set_banwords_cache(group_id, banwords, config.TTL_BANWORDS)

        self._banwords_ram[group_id] = (expires_at, banwords)
        return banwords

    def add_banword(self, group_id: int, pattern: str, reply: str) -> bool:
        try:
            re.compile(pattern)
        except re.error as e:
            logger.warning(f"Паттерн отклонён, не компилируется: {e}")
            return False

        added = self.db.add_banword(group_id, pattern, reply)
        if added:
            self.db.invalidate_banwords_cache(group_id)
            self._banwords_ram.pop(group_id, None)
        return added

    def get_valid_banwords(self, group_id: int) -> List[Banword]:
        valid = []
        for banword in self._get_banwords_cached(group_id):
            if banword.pattern in self._bad_patterns:
                continue
            try:
                re.compile(banword.pattern)
                valid.append(banword)
            except re.error as e:
                logger.warning(f"Банворд {banword} пропущен, паттерн не компилируется: {e}")
                self._bad_patterns.add(banword.pattern)
        return valid

    def parse_comment_template(self, comment_text: str) -> str:
        templates = re.findall(r"{{\w+}}", comment_text)
        for template in templates:
            key = template.strip("{}")
            if key in self.faker_replace:
                comment_text = comment_text.replace(template, self.faker_replace[key]())
        return comment_text
