from types import SimpleNamespace

from src.bot.services.comments import CommentsManager
from src.database.models import PermissionLevel, User


class FakeLogsManager:
    def __init__(self):
        self.entries = []
        self.info = {}

    def get_bot_message_info(self, message_id):
        return self.info.get(message_id, {})

    def get_message_info(self, message_id):
        return self.info.get(message_id)

    def add_message_log(self, bot_msg_id, chat_id, message_id, text):
        self.entries.append({"bot_msg_id": bot_msg_id, "chat_id": chat_id, "text": text})


class FakeBot:
    def __init__(self, db, logger_chat_id="-100555", base_url="http://test"):
        self.db = db
        self.config = SimpleNamespace(
            LOGGER_CHAT_ID=str(logger_chat_id),
            BASE_URL=base_url,
            IGNORING_CHAT_IDS=[],
        )
        self.comments_manager = CommentsManager(db)
        self.logs_manager = FakeLogsManager()
        self.calls = []
        self.forwarded = []

    def send_message(
        self,
        chat_id,
        text,
        reply_to_message_id=None,
        reply_markup=None,
        parse_mode="HTML",
        escape=False,
    ):
        self.calls.append(
            {
                "chat_id": chat_id,
                "text": text,
                "reply_to_message_id": reply_to_message_id,
                "reply_markup": reply_markup,
                "escape": escape,
            }
        )
        return {"ok": True, "result": {"message_id": len(self.calls)}}

    def get_chat_info(self, chat_id):
        return {}

    def check_banwords(self, message_data):
        pass

    def handle_forwarded_message(self, message_data):
        self.forwarded.append(message_data)

    @property
    def texts(self):
        return [call["text"] for call in self.calls]

    @property
    def last(self):
        return self.calls[-1]["text"] if self.calls else None


def make_message(
    chat_id,
    user_id,
    text,
    chat_type="group",
    username="tester",
    message_id=42,
):
    return {
        "chat": {"id": chat_id, "type": chat_type},
        "from": {"id": user_id, "username": username},
        "text": text,
        "message_id": message_id,
    }


def add_user(db, group_id, user_id, level=PermissionLevel.BASE):
    return db.add_user(
        User(tg_group_id=group_id, tg_user_id=user_id, username=f"u{user_id}", permission=level)
    )
