import logging
from database.models import PermissionLevel
from typing import Callable, Any
from functools import wraps

logger = logging.getLogger(__name__)


def required_permission(permission_level: PermissionLevel) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, message_data, *args, **kwargs) -> Any:
            try:
                if not isinstance(message_data, dict):
                    logger.error(f"Invalid message_data type: {type(message_data)}")
                    return self._send_permission_error(
                        chat_id, message_data, ValueError("Invalid message_data type")
                    )
                chat_id = message_data.get("chat", {}).get("id")
                user_id = message_data.get("from", {}).get("id")

                if not chat_id or not user_id:
                    logger.error("Не удалось получить chat_id или user_id")
                    return
                user = self.bot.db.get_user(user_id, chat_id)

                if not user:
                    if (
                        permission_level <= PermissionLevel.BASE
                        or chat_id == self.bot.config.LOGGER_CHAT_ID
                    ):
                        return func(self, message_data, *args, **kwargs)

                    return self._send_user_not_found(chat_id, message_data)

                if user.permission >= permission_level:
                    return func(self, message_data, *args, **kwargs)
                else:
                    return self._send_insufficient_permissions(
                        chat_id, message_data, user.permission, permission_level
                    )
            except Exception as e:
                logger.error(f"Error in permission check: {e}")
                return self._send_permission_error(chat_id, message_data, e)

        return wrapper

    return decorator
