from enum import IntEnum
import json
import os
import random
import re
from typing import Optional
from faker import Faker
import logging

logger = logging.getLogger(__name__)


class CommentsManager:
    def __init__(self, comments_file: str):
        self.comments_file = comments_file
        self.faker = Faker("ru_RU")
        self.faker_replace = {
            "name": lambda: self.faker.name(),
            "address": lambda: self.faker.address(),
            "phone_number": lambda: self.faker.phone_number(),
            "company": lambda: self.faker.company(),
        }
        self.comment_data = {}
        self._load_comments()

    def _load_comments(self) -> None:
        try:
            if os.path.exists(self.comments_file):
                with open(self.comments_file, "r", encoding="utf-8") as file:
                    self.comment_data = json.load(file)
        except Exception as e:
            logger.error(f"Error loading comments: {e}")

    def save_comments(self) -> None:
        try:
            with open(self.comments_file, "w", encoding="utf-8") as file:
                json.dump(self.comment_data, file, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving comments: {e}")

    def init_group_comments(self, group_id: int) -> None:
        group_name = "group_" + str(abs(group_id))

        self.comment_data[group_name] = {
            "text": ["круто"],
            "photo": ["восхитительно"],
            "scheduled": {},
        }
        self.save_comments()
        logger.info(f"Initialized comments for group {group_id}")
        logger.info(f"Current comment data: {self.comment_data[group_name]}")

    def add_comment(self, comment_type: str, text: str, group_id: int) -> bool:
        group_name = "group_" + str(abs(group_id))
        if group_name not in self.comment_data:
            self.init_group_comments(group_id)

        if text in self.comment_data[group_name][comment_type]:
            return False

        self.comment_data[group_name][comment_type].append(text)
        self.save_comments()
        return True

    def add_scheduled_comment(self, text: str, group_id: int, date: str) -> bool:
        group_name = "group_" + str(abs(group_id))
        if group_name not in self.comment_data:
            self.init_group_comments(group_id)

        if date not in self.comment_data[group_name]["scheduled"]:
            self.comment_data[group_name]["scheduled"][date] = []
            # self.save_comments()

        if text in self.comment_data[group_name]["scheduled"][date]:
            return False

        self.comment_data[group_name]["scheduled"][date].append(text)
        self.save_comments()
        return True

    def delete_comment(
        self, group_id: int, comment_type: str, index: int
    ) -> Optional[str]:
        group_name = "group_" + str(abs(group_id))
        if comment_type not in ["text", "photo", "scheduled"]:
            return
        if (
            group_name not in self.comment_data
            or not self.comment_data[group_name][comment_type]
        ):
            logger.warning("Group not found in comment data")
            self.init_group_comments(group_id)
            return None

        if comment_type == "scheduled":
            # Для запланированных комментариев: index - это 1-based общий индекс
            dates = sorted(self.comment_data[group_name]["scheduled"].keys())
            current_index = 1  # начинаем с 1

            for date in dates:
                comments = self.comment_data[group_name]["scheduled"][date]
                if not isinstance(comments, list):
                    continue

                if current_index <= index < current_index + len(comments):
                    # Нашли нужный индекс
                    local_index = index - current_index
                    deleted = comments.pop(local_index)

                    # Если список комментариев для даты стал пустым, удаляем дату
                    if not comments:
                        del self.comment_data[group_name]["scheduled"][date]

                    self.save_comments()
                    return deleted

                current_index += len(comments)
            return None

        elif comment_type in ["text", "photo"]:
            if 0 <= index <= len(self.comment_data[group_name][comment_type]):
                deleted = self.comment_data[group_name][comment_type].pop(index - 1)
                self.save_comments()
                return deleted
        return None

    def get_random_comment(self, group_id: int, comment_type: str) -> Optional[str]:
        group_name = "group_" + str(abs(group_id))
        if group_name not in self.comment_data:
            self.init_group_comments(group_id)

        if (
            comment_type in ["text", "photo"]
            and self.comment_data[group_name][comment_type]
        ):
            return random.choice(self.comment_data[group_name][comment_type])

    def parse_comment_template(self, comment: str) -> str:
        templates = re.findall(r"{{\w+}}", comment)
        for template in templates:
            key = template.replace("{{", "").replace("}}", "")
            if key in self.faker_replace:
                comment = comment.replace(template, self.faker_replace[key]())
        return comment
