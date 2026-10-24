from html import escape
from typing import Dict, Any, Optional

from src.database.models import PermissionLevel, User, CommentTypes, Comment
from src.bot.utils.permissions import required_permission

from src.shared.logger import get_bot_logger

logger = get_bot_logger()


class MessageHandler:
    def __init__(self, bot):
        self.bot = bot
        self.help_msg = self._create_help_message()

        self.private_commands = {
            "/start": self.handle_start,
            "/help": self.handle_help,
            "/admin_msg": self.handle_admin_msg,
            "/answer": self.handle_answer,
            "/get_user_info": self.handle_get_user_info,
        }

        self.group_commands = {
            "/start": self.handle_start,
            "/help": self.handle_help,
            "/admin_msg": self.handle_admin_msg,
            "/register": self.handle_register,
            "/get_banwords": self.handle_get_banwords,
            "/unregister": self.handle_unregister,
            "/add_comment": self.handle_add_comment,
            "/comment_list": self.handle_list_comment,
            "/delete_comment": self.handle_delete_comment,
            "/set_permission": self.handle_set_permission,
            "/set_schedule_comment": self.handle_set_schedule_comment,
            "/get_users_list": self.handle_get_users_list,
            "/get_user_info": self.handle_get_user_info,
        }

    def _create_help_message(self) -> str:
        return (
            f"/help - помощь - доступно от {PermissionLevel.BASE.to_string()}\n"
            f"/register - зарегистрироваться - доступно от {PermissionLevel.BASE.to_string()}\n"
            f"/unregister - удалить себя из базы - доступно от {PermissionLevel.BASE.to_string()}\n"
            f"/get_banwords - получить список запрещенных слов - доступно от {PermissionLevel.BASE.to_string()}\n"
            f"/admin_msg [text] - отправить сообщение админу - доступно от {PermissionLevel.BASE.to_string()}\n"
            f"/get_users_list - получить список пользователей - доступно от {PermissionLevel.BASE.to_string()}\n"
            f"/comment_list - список комментов - доступно от {PermissionLevel.BASE.to_string()}\n"
            f"/add_comment [text | photo] [text] - доступно от {PermissionLevel.MODER.to_string()}\n"
            f"/delete_comment [text | photo] [id] - доступно от {PermissionLevel.MODER.to_string()}\n"
            f"/set_permission [username] [permission] - доступно от {PermissionLevel.ADMIN.to_string()}\n"
            f"/set_schedule_comment [command | null] - доступно от {PermissionLevel.DEV.to_string()}\n"
            f"/get_user_info [chat_id | username] - доступно от {PermissionLevel.DEV.to_string()}\n"
            f"/answer [text] - уникальная команда - доступно от {PermissionLevel.LOGGER.to_string()}"
        )

    def _parse_command(self, text: str) -> Optional[str]:
        if not text or not text.startswith("/"):
            return None
        first_word = text.split(None, 1)[0]
        return first_word.split("@", 1)[0].lower()

    def process_message(self, message_data: Dict[str, Any]) -> None:
        logger.info("Начало обработки сообщения")

        try:
            chat_data = message_data.get("chat") or {}
            from_data = message_data.get("from") or {}

            chat_id = chat_data.get("id")
            user_id = from_data.get("id")
            username = from_data.get("username", "")
            text = message_data.get("text", " ")
            chat_type = chat_data.get("type", "")

            logger.debug(f"{chat_data=}")
            logger.debug(f"{from_data=}")
            logger.debug(f"Обработка сообщения: чат {chat_id}, тип {chat_type}, текст: {text}")
            logger.debug(f"Полные данные сообщения: {message_data}")

            if user_id and username != "GroupAnonymousBot":
                self.bot.db.check_username(user_id, username)

            self.bot.check_banwords(message_data)

            if chat_type in ["group", "supergroup"]:
                self.handle_group_message(message_data)

            elif chat_type == "private":
                self.handle_private_message(message_data)

        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")

    def handle_command(self, message_data: Dict[str, Any]) -> bool:
        text = message_data.get("text") or ""
        chat_type = message_data.get("chat", {}).get("type", "")

        name = self._parse_command(text)
        if name is None:
            return False

        handler = self.private_commands.get(name) or self.group_commands.get(name)
        if handler is None:
            return False

        if chat_type == "private":
            if name not in self.private_commands:
                self.bot.send_message(
                    message_data["chat"]["id"],
                    "не могу выполнить в лс",
                    reply_to_message_id=message_data["message_id"],
                )
                return True
        elif name not in self.group_commands:
            return False

        logger.info(f"Вызвана команда: {name}")
        handler(message_data)
        return True

    @required_permission(PermissionLevel.BASE)
    def handle_start(self, message_data: Dict[str, Any]) -> None:
        chat_id = message_data["chat"]["id"]
        chat_type = message_data["chat"].get("type", "")
        if chat_type == "private":
            self.bot.send_message(
                chat_id,
                "привет, я бот для комментов, напиши /register в группе чтобы зарегистрироваться",
            )
        else:
            self.bot.send_message(
                chat_id,
                "чтобы зарегистрироваться напиши /register",
            )

    @required_permission(PermissionLevel.BASE)
    def handle_get_banwords(self, message_data: Dict[str, Any]) -> None:
        chat_id = message_data["chat"]["id"]
        banwords = self.bot.comments_manager.get_banwords_list(chat_id)
        msg = ""
        for banword in banwords:
            msg += f"<b>{escape(banword.pattern)}</b> - {escape(banword.reply)}\n"

        if msg:
            self.bot.send_message(chat_id, msg, reply_to_message_id=message_data["message_id"])
        else:
            self.bot.send_message(chat_id, "нет банвордов")

    def handle_private_message(self, message_data: Dict[str, Any]) -> None:
        chat_id = message_data["chat"]["id"]
        text = message_data.get("text", "")
        message_id = message_data.get("message_id")

        if not (str(chat_id) == self.bot.config.LOGGER_CHAT_ID):
            self._log_private_message(message_data)

        self.handle_command(message_data)

        if text and not text.startswith("/"):
            text = "мармелад" if "мармелад" not in text.lower().strip() else "нет"
            self.bot.send_message(chat_id, text, reply_to_message_id=message_id)

    def handle_group_message(self, message_data: Dict[str, Any]) -> None:
        logger.info("Обработка сообщения в группе")
        chat_id = message_data["chat"]["id"]
        is_forwarded = any(
            key.startswith("forward") for key in message_data.keys()
        ) and message_data.get("is_automatic_forward")
        self._log_group_message(message_data, is_forwarded)

        if str(chat_id) in self.bot.config.IGNORING_CHAT_IDS:
            self.bot.send_message(chat_id, "я не буду здесь работать")
            return

        text = message_data.get("text", "")

        if text.startswith("/"):
            self.handle_command(message_data)
            return

        if is_forwarded:
            self.bot.handle_forwarded_message(message_data)

    def _log_private_message(self, message_data: Dict[str, Any]) -> None:
        from src.shared.time_utils import get_moscow_datetime_str

        chat_id = message_data["chat"]["id"]
        text = message_data.get("text", "")
        message_id = message_data.get("message_id")

        chat_info = self.bot.get_chat_info(chat_id)
        username = chat_info.get("username", "неизвестно")

        log_message = (
            f"[{get_moscow_datetime_str()} : @{escape(username)} ({chat_id}), {escape(text)}]"
        )

        reply_to = None
        log_entry = self.bot.logs_manager.get_bot_message_info(
            message_data.get("reply_to_message", {}).get("message_id", {})
        )
        if log_entry:
            reply_to = int(list(log_entry.keys())[0])

        msg_result = self.bot.send_message(self.bot.config.LOGGER_CHAT_ID, log_message, reply_to)

        if msg_result and isinstance(msg_result, dict) and msg_result.get("ok"):
            bot_msg_id = msg_result.get("result", {}).get("message_id")
            if bot_msg_id:
                self.bot.logs_manager.add_message_log(bot_msg_id, chat_id, message_id, text)

    def _log_group_message(self, message_data: Dict[str, Any], is_forwared: bool) -> None:
        from src.shared.time_utils import get_moscow_datetime_str

        try:
            chat_id = message_data["chat"]["id"]
            text = message_data.get("text", "")
            message_id = message_data.get("message_id")
            caption = message_data.get("caption", "")

            from_user = message_data.get("from", {})
            username = from_user.get("username", "неизвестно")

            channel_info = self._get_forwarded_channel_info(message_data)
            group_type = "ГРУППЫ" if not is_forwared else "КАНАЛА"
            channel_text = (
                f"СООБЩЕНИЕ ИЗ {group_type} {escape(channel_info)}"
                if channel_info
                else f"СООБЩЕНИЕ ИЗ {group_type}"
            )
            reply_to_msg_id = message_data.get("reply_to_message", {}).get("message_id")
            reply_to = None
            if reply_to_msg_id:
                log_entry = self.bot.logs_manager.get_bot_message_info(reply_to_msg_id)
                if log_entry:
                    reply_to = int(list(log_entry.keys())[0])
        except Exception as e:
            logger.error(f"Ошибка при логировании сообщения: {e}")
            return

        log_message = (
            f"{channel_text}\n"
            f"[{get_moscow_datetime_str()} : @{escape(username)} ({chat_id}), "
            f"{escape(text or caption or 'нет текста')}]"
        )
        logger.info(f"{log_message=}")

        msg_result = self.bot.send_message(self.bot.config.LOGGER_CHAT_ID, log_message, reply_to)
        logger.info(f"{msg_result=}")

        if msg_result:
            if isinstance(msg_result, list):
                for result in msg_result:
                    if result and isinstance(result, dict) and result.get("ok"):
                        bot_msg_id = result.get("result", {}).get("message_id")
                        if bot_msg_id:
                            logger.info(f"==Сообщение отправлено в лог: {bot_msg_id}")
                            self.bot.logs_manager.add_message_log(
                                bot_msg_id, chat_id, message_id, text or caption
                            )

                            logger.info("сообщение отправлено в лог")

            elif isinstance(msg_result, dict) and msg_result.get("ok"):
                bot_msg_id = msg_result.get("result", {}).get("message_id")
                if bot_msg_id:
                    logger.info(f"==Сообщение отправлено в лог: {bot_msg_id}")
                    self.bot.logs_manager.add_message_log(
                        bot_msg_id, chat_id, message_id, text or caption
                    )
                    logger.info("сообщение отправлено в лог")

    def _get_forwarded_channel_info(self, message_data: Dict[str, Any]) -> str:
        sender_chat = message_data.get("sender_chat")
        if sender_chat and isinstance(sender_chat, dict):
            return sender_chat.get("title", "")
        return ""

    def _send_user_not_found(self, chat_id: int, message_data: Dict[str, Any]) -> None:
        try:
            keyboard = {
                "inline_keyboard": [
                    [
                        {
                            "text": "БАГ РЕПОРТ",
                            "url": f"{self.bot.config.BASE_URL}/admin_msg",
                        }
                    ]
                ]
            }
            self.bot.send_message(
                chat_id,
                "пользователь не найден,используйте /register или обратитесь к разработчику",
                reply_to_message_id=message_data["message_id"],
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения о не найденном пользователе: {e}")

    def _send_insufficient_permissions(
        self,
        chat_id: int,
        message_data: Dict[str, Any],
        user_permission: PermissionLevel,
        required_permission: PermissionLevel,
    ) -> None:

        self.bot.send_message(
            chat_id,
            f'недостаточно прав. минимальный уровень прав "{required_permission.to_string()}",\n'
            f'ваши права "{user_permission.to_string()}"',
            reply_to_message_id=message_data["message_id"],
        )

    def _send_permission_error(
        self, chat_id: int, message_data: Dict[str, Any], error: Exception
    ) -> None:
        try:
            keyboard = {
                "inline_keyboard": [
                    [
                        {
                            "text": "БАГ РЕПОРТ",
                            "url": f"{self.bot.config.BASE_URL}/admin_msg",
                        }
                    ]
                ]
            }
            self.bot.send_message(
                chat_id,
                f"ошибка при проверке прав: {type(error).__name__}, обратитесь к разработчику",
                reply_to_message_id=message_data["message_id"],
                reply_markup=keyboard,
            )

        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения об ошибке прав: {e}")

    # ========== КОМАНДЫ ГРУПП ==========
    @required_permission(PermissionLevel.BASE)
    def handle_register(self, message_data: Dict[str, Any]) -> None:
        chat_id = message_data["chat"]["id"]
        user_id = message_data["from"]["id"]
        message_id = message_data["message_id"]

        username = message_data["from"].get("username", "")

        group_users = self.bot.db.get_users_in_group(chat_id)

        # Если это первый пользователь или анонимный админ
        if len(group_users) <= 0 or username == "GroupAnonymousBot":
            permission = PermissionLevel.DEV
            # Генерируем уникальный юзернейм для анонимного админа
            if username == "GroupAnonymousBot":
                import uuid

                # Создаем уникальный идентификатор
                unique_id = str(uuid.uuid4())[:8]  # Берем первые 8 символов UUID
                username = f"AnonymousAdmin_{unique_id}"
        else:
            permission = PermissionLevel.BASE

        user = User(
            tg_user_id=user_id,
            username=username,
            permission=permission,
            tg_group_id=chat_id,
        )

        success = self.bot.db.add_user(user)

        if success:
            self.bot.comments_manager.init_group_comments(chat_id)

            self.bot.send_message(
                chat_id, "Вы успешно зарегистрированы!", reply_to_message_id=message_id
            )

            display_name = username or f"id_{user_id}"
            self.bot.send_message(
                self.bot.config.LOGGER_CHAT_ID,
                f"Новый пользователь: @{display_name}",
            )
        else:
            self.bot.send_message(
                chat_id, "Вы уже зарегистрированы!", reply_to_message_id=message_id
            )

    @required_permission(PermissionLevel.BASE)
    def handle_help(self, message_data: Dict[str, Any]) -> None:
        chat_id = message_data["chat"]["id"]
        self.bot.send_message(chat_id, self.help_msg)

    @required_permission(PermissionLevel.BASE)
    def handle_unregister(self, message_data: Dict[str, Any]) -> None:
        try:
            user_id = message_data["from"]["id"]
            chat_id = message_data["chat"]["id"]
            delete_user = self.bot.db.get_user(user_id, chat_id)
            if delete_user:
                success = self.bot.db.delete_user(delete_user)
                if success:
                    self.bot.send_message(
                        chat_id,
                        "Вы успешно удалены из списка пользователей!",
                        reply_to_message_id=message_data.get("message_id"),
                    )
                else:
                    self.bot.send_message(
                        chat_id,
                        "Произошла ошибка при удалении пользователя. Попробуйте позже.",
                        reply_to_message_id=message_data.get("message_id"),
                    )
        except Exception as e:
            logger.error(f"Error in handle_unregister: {e}")
            self.bot.send_message(
                chat_id,
                "Произошла ошибка",
                reply_to_message_id=message_data.get("message_id"),
            )

    @required_permission(PermissionLevel.BASE)
    def handle_get_users_list(self, message_data: Dict[str, Any]) -> None:
        chat_id = message_data["chat"]["id"]

        users = self.bot.db.get_users_in_group(chat_id)

        if not users:
            self.bot.send_message(
                chat_id,
                "В этой группе пока нет зарегистрированных пользователей",
                reply_to_message_id=message_data.get("message_id"),
            )
            return

        msg_lines = ["Список пользователей в этой группе:"]
        for user in users:
            display_name = user.username or f"id_{user.tg_user_id}"
            msg_lines.append(f"@{display_name} - {user.permission.to_string()}")

        self.bot.send_message(
            chat_id,
            "\n".join(msg_lines),
            reply_to_message_id=message_data.get("message_id"),
        )

    @required_permission(PermissionLevel.BASE)
    def handle_list_comment(self, message_data: Dict[str, Any]) -> None:
        chat_id = message_data["chat"]["id"]
        group_comments = self.bot.comments_manager.get_comments_list(chat_id)
        if (
            not group_comments[CommentTypes.TEXT.value]
            and not group_comments[CommentTypes.PHOTO.value]
            and not group_comments[CommentTypes.SCHEDULED.value]
        ):
            self.bot.send_message(
                chat_id,
                "Для этой группы еще нет комментариев",
                reply_to_message_id=message_data.get("message_id"),
            )
            return

        msg_lines = []
        num = 1

        text_comments = group_comments.get(CommentTypes.TEXT.value, [])
        if text_comments:
            msg_lines.append("ТЕКСТОВЫЕ".center(50, "="))
            for comment in text_comments:
                raw = comment.comment_text
                parsed = self.bot.comments_manager.parse_comment_template(raw)
                if parsed != raw:
                    msg_lines.append(f"{num}. {escape(raw)} ( {escape(parsed)} )")
                else:
                    msg_lines.append(f"{num}. {escape(raw)}")
                num += 1
        num = 1
        photo_comments = group_comments.get(CommentTypes.PHOTO.value, [])
        if photo_comments:
            msg_lines.append("ФОТО".center(50, "="))
            for comment in photo_comments:
                raw = comment.comment_text
                parsed = self.bot.comments_manager.parse_comment_template(raw)
                if parsed != raw:
                    msg_lines.append(f"{num}. {escape(raw)} ( {escape(parsed)} )")
                else:
                    msg_lines.append(f"{num}. {escape(raw)}")
                num += 1
        num = 1
        scheduled_comments = group_comments.get(CommentTypes.SCHEDULED.value, {})
        if scheduled_comments:
            msg_lines.append("ЗАПЛАНИРОВАННЫЕ".center(50, "="))

            for date, comments in scheduled_comments.items():
                msg_lines.append(f"{date}".center(30, "-"))
                for comment in comments:
                    msg_lines.append(f"  {num}. {escape(comment.comment_text)}")
                    num += 1

        if msg_lines:
            self.bot.send_message(
                chat_id,
                "\n".join(msg_lines),
                reply_to_message_id=message_data.get("message_id"),
            )
        else:
            self.bot.send_message(
                chat_id,
                "Нет комментариев для отображения",
                reply_to_message_id=message_data.get("message_id"),
            )

    @required_permission(PermissionLevel.MODER)
    def handle_add_comment(self, message_data: Dict[str, Any]) -> None:
        chat_id = message_data["chat"]["id"]
        text = message_data.get("text", "")
        msg_id = message_data.get("message_id")

        parts = text.split()
        if len(parts) < 3:
            self.bot.send_message(
                chat_id,
                "Используйте /add_comment [text|photo] текст",
                reply_to_message_id=msg_id,
            )
            return

        comment_type = CommentTypes.from_str(parts[1])
        comment_text = " ".join(parts[2:])

        if comment_type not in [CommentTypes.TEXT, CommentTypes.PHOTO]:
            self.bot.send_message(
                chat_id,
                "Неверный тип комментария",
                reply_to_message_id=msg_id,
            )
            return

        success = self.bot.comments_manager.add_comment(
            Comment(group_id=chat_id, comment_type=comment_type, comment_text=comment_text)
        )

        if success:
            self.bot.send_message(
                chat_id,
                f"Добавлен {comment_type.value}-комментарий: {escape(comment_text)}",
                reply_to_message_id=msg_id,
            )
        else:
            self.bot.send_message(
                chat_id, "Такой комментарий уже существует", reply_to_message_id=msg_id
            )

    @required_permission(PermissionLevel.MODER)
    def handle_delete_comment(self, message_data: Dict[str, Any]) -> None:

        chat_id = message_data["chat"]["id"]
        text = message_data.get("text", "")
        msg_id = message_data.get("message_id")

        parts = text.split()
        if len(parts) < 3:
            self.bot.send_message(
                chat_id,
                "/delete_comment [text | photo | scheduled] [номер]",
                reply_to_message_id=msg_id,
            )
            return

        comment_type = CommentTypes.from_str(parts[1])
        if not comment_type:
            self.bot.send_message(
                chat_id,
                "Неверный тип комментария",
                reply_to_message_id=msg_id,
            )
            return
        index_str = parts[2]

        if not index_str.isdigit():
            self.bot.send_message(chat_id, "Введите число", reply_to_message_id=msg_id)
            return

        index = int(index_str)

        deleted_comment = self.bot.comments_manager.delete_comment(chat_id, comment_type, index)

        if deleted_comment:
            self.bot.send_message(
                chat_id,
                f"Комментарий №{index} ({escape(deleted_comment.comment_text)}) удален",
                reply_to_message_id=msg_id,
            )
        else:
            self.bot.send_message(
                chat_id,
                f"{comment_type.value} Комментарий №{index} не найден",
                reply_to_message_id=msg_id,
            )

    @required_permission(PermissionLevel.ADMIN)
    def handle_set_permission(self, message_data: Dict[str, Any]) -> None:
        chat_id = message_data["chat"]["id"]
        user_id = message_data["from"]["id"]
        text = message_data.get("text", "")
        msg_id = message_data.get("message_id")
        reply = message_data.get("reply_to_message")

        parts = text.split()
        if reply and len(parts) == 2:
            permission_str = parts[1]
            target_id = (reply.get("from") or {}).get("id")
            if not target_id:
                self.bot.send_message(
                    chat_id,
                    "Не удалось определить пользователя из ответа",
                    reply_to_message_id=msg_id,
                )
                return
            target_user = self.bot.db.get_user(target_id, chat_id)
        elif len(parts) == 3:
            _, username, permission_str = parts

            if username.startswith("@"):
                username = username[1:]

            target_user = self.bot.db.get_user_by_username(username, chat_id)
        else:
            self.bot.send_message(
                chat_id,
                "Используйте: /set_permission [username] [permission] "
                "или ответьте на сообщение: /set_permission [permission]",
                reply_to_message_id=msg_id,
            )
            return

        new_permission = PermissionLevel.from_string(permission_str)
        if new_permission is None:
            self.bot.send_message(
                chat_id,
                "Неверное значение разрешения (BASE,MODER,ADMIN,DEV,LOGGER)",
                reply_to_message_id=msg_id,
            )
            return

        if not target_user:
            self.bot.send_message(chat_id, "Пользователь не найден", reply_to_message_id=msg_id)
            return

        username = target_user.username or f"id_{target_user.tg_user_id}"

        current_user = self.bot.db.get_user(user_id, chat_id)

        can_change = (
            (
                current_user.permission > target_user.permission
                and current_user.permission >= new_permission
            )
            or (
                current_user.permission == PermissionLevel.DEV
                and target_user.permission != PermissionLevel.DEV
            )
            or (str(user_id) == str(self.bot.config.LOGGER_CHAT_ID))
        )

        if not can_change:
            self.bot.send_message(
                chat_id,
                "Недостаточно прав для изменения прав этого пользователя",
                reply_to_message_id=msg_id,
            )
            return

        success = self.bot.db.update_user_permission(target_user, new_permission)

        if success:
            self.bot.send_message(
                chat_id,
                f"Успешно! @{username} теперь имеет права {new_permission.to_string()}",
                reply_to_message_id=msg_id,
            )
        else:
            self.bot.send_message(chat_id, "Ошибка при обновлении прав", reply_to_message_id=msg_id)

    @required_permission(PermissionLevel.DEV)
    def handle_set_schedule_comment(self, message_data: Dict[str, Any]) -> None:
        logger.info(f"handle_set_schedule_comment: {message_data}")
        chat_id = message_data["chat"]["id"]
        text = message_data.get("text", "")
        msg_id = message_data.get("message_id")

        parts = text.split()

        if len(parts) < 3:
            keyboard = {
                "inline_keyboard": [
                    [
                        {
                            "text": "Запланировать комментарий",
                            "url": f"{self.bot.config.BASE_URL}/date_picker",
                        }
                    ]
                ]
            }

            self.bot.send_message(
                chat_id,
                "нажми на кнопку чтобы запланировать комментарий",
                reply_to_message_id=msg_id,
                reply_markup=keyboard,
            )
            return

        date = parts[1]

        if not Comment.parse_scheduled_date(date):
            self.bot.send_message(
                chat_id,
                "Дата должна быть строго в формате ГГГГ-ММ-ДД и не раньше текущего дня",
                reply_to_message_id=msg_id,
            )
            return
        comment_text = " ".join(parts[2:])

        success = self.bot.comments_manager.add_comment(
            Comment(chat_id, CommentTypes.SCHEDULED, comment_text, date)
        )

        if success:
            self.bot.send_message(
                chat_id,
                f"Комментарий <code>{escape(comment_text)}</code> добавлен на дату {date}",
                reply_to_message_id=msg_id,
            )
        else:
            self.bot.send_message(
                chat_id,
                "Такой комментарий уже запланирован на эту дату",
                reply_to_message_id=msg_id,
            )

    @required_permission(PermissionLevel.BASE)
    def handle_admin_msg(self, message_data: Dict[str, Any]) -> None:
        chat_id = message_data["chat"]["id"]
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "СООБЩЕНИЕ АДМИНУ",
                        "url": f"{self.bot.config.BASE_URL}/admin_msg",
                    }
                ]
            ]
        }

        self.bot.send_message(
            chat_id,
            "обратитесь к разработчику",
            reply_to_message_id=message_data.get("message_id"),
            reply_markup=keyboard,
        )

    @required_permission(PermissionLevel.DEV)
    def handle_get_user_info(self, message_data):
        chat_id = message_data["chat"]["id"]
        is_private = message_data["chat"]["type"] == "private"
        parts = message_data.get("text", "").split()
        if len(parts) < 2:
            self.bot.send_message(chat_id, "Используйте: /get_user_info [chat_id | username]")
            return
        identifier = parts[1].lstrip("@")
        if identifier.lstrip("-").isdecimal():
            self._show_chat_info(chat_id, int(identifier), is_private)
        else:
            self._show_user_info(chat_id, identifier, is_private)

    def _show_chat_info(self, chat_id, target_chat_id, is_private):
        info = self.bot.get_chat_info(target_chat_id)
        if not info:
            self.bot.send_message(chat_id, "Не удалось получить информацию")
            return
        permission_info = ""
        if not is_private:
            u = self.bot.db.get_user(target_chat_id, chat_id)
            permission_info = (
                f"\nПрава в этой группе: {u.permission.to_string()}"
                if u
                else "\nПользователь не зарегистрирован в этой группе"
            )
        self.bot.send_message(chat_id, self._fmt_chat(target_chat_id, info, permission_info))

    def _show_user_info(self, chat_id, username, is_private):
        if is_private:
            users = self.bot.db.get_user_by_username(username)  # всегда список
            if not users:
                self.bot.send_message(chat_id, "Пользователь не найден")
                return
            info = self.bot.get_chat_info(users[0].tg_user_id)
            if not info:
                self.bot.send_message(chat_id, "Не удалось получить информацию")
                return
            lines = [self._fmt_profile(username, info), f"Найден в {len(users)} группе(ах):"]
            for i, u in enumerate(users, 1):
                title = self.bot.get_chat_info(u.tg_group_id).get("title", "неизвестно")
                lines.append(
                    f"{i}. Группа: {u.tg_group_id} ({title}), Права: {u.permission.to_string()}"
                )
            self.bot.send_message(chat_id, "\n".join(lines))
        else:
            u = self.bot.db.get_user_by_username(username, chat_id)  # User|None
            if not u:
                self.bot.send_message(chat_id, "Пользователь не зарегистрирован в этой группе")
                return
            info = self.bot.get_chat_info(u.tg_user_id)
            if not info:
                self.bot.send_message(chat_id, "Не удалось получить информацию")
                return
            self.bot.send_message(
                chat_id,
                self._fmt_profile(username, info)
                + f"\nПрава в этой группе: {u.permission.to_string()}",
            )

    def handle_answer(self, message_data: Dict[str, Any]) -> None:
        chat_id = message_data["chat"]["id"]
        text = message_data.get("text", "")

        if str(chat_id) != self.bot.config.LOGGER_CHAT_ID:
            return

        reply_to_message = message_data.get("reply_to_message")
        if not reply_to_message:
            self.bot.send_message(chat_id, "Это сообщение не является ответом на другое сообщение")
            return

        replied_message_id = reply_to_message.get("message_id")
        if not replied_message_id:
            self.bot.send_message(
                chat_id, "Не удалось определить сообщение, на которое вы ответили"
            )
            return
        log_entry = self.bot.logs_manager.get_message_info(replied_message_id)
        if not log_entry:
            self.bot.send_message(chat_id, f"Сообщение {replied_message_id} не найдено в логах")
            return

        parts = text.split(" ", 1)
        if len(parts) < 2:
            self.bot.send_message(chat_id, "Используйте: /answer [текст ответа]")
            return

        answer_text = parts[1]

        self.bot.send_message(
            log_entry["chat_id"],
            answer_text,
            reply_to_message_id=log_entry["message_id"],
        )

        self.bot.send_message(chat_id, "Ответ отправлен")

    @staticmethod
    def _fmt_profile(identifier: str, info: Dict[str, Any]) -> str:
        return (
            f"Данные по пользователю @{identifier}:\n"
            f"ID: {info.get('id')}\n"
            f"Имя: {info.get('first_name', 'Не указано')}\n"
            f"Фамилия: {info.get('last_name', 'Не указана')}\n"
            f"Username: @{info.get('username', 'Не указан')}"
        )

    @staticmethod
    def _fmt_chat(target_chat_id: int, info: Dict[str, Any], permission_info: str = "") -> str:
        return (
            f"Данные по чату {target_chat_id}:\n"
            f"ID: {info.get('id')}\n"
            f"Username: @{info.get('username', 'Не указан')}"
            f"{permission_info}"
        )
