import random
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReactionTypeEmoji
from aiogram.filters import Command, CommandStart
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramRetryAfter
import asyncio
import logging
from dotenv import load_dotenv
from os import getenv
from comments import comments, ph_comments
from banwords import banwords

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=getenv("BOT_TOKEN"))
dp = Dispatcher()


# Команда /start - работает везде
@dp.message(CommandStart())
async def start_command(message: types.Message):
    if message.chat.type == ChatType.PRIVATE:
        msg = []
        for c in comments:
            if callable(c):
                comm = c()
            else:
                comm = c
            msg.append("-- " + comm)
        msg.append("PHOTO".center(60, "="))
        for c in ph_comments:
            if callable(c):
                comm = c()
            else:
                comm = c
            msg.append("-- " + comm)
        await message.reply("\n".join(msg))
    else:
        await message.answer("Привет! Я бот этой группы.")


async def set_reaction_with_retry(chat_id: int, message_id: int):
    """Функция для установки реакции с обработкой ограничений"""
    try:
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji="🗿")],
        )
    except TelegramRetryAfter as e:
        logger.warning(f"Flood control. Waiting {e.retry_after} seconds")
        await asyncio.sleep(e.retry_after)
        await set_reaction_with_retry(chat_id, message_id)  # Рекурсивный повтор
    except Exception as e:
        logger.error(f"Error setting reaction: {e}")


# Обработчик ВСЕХ сообщений в группах
@dp.message(F.chat.type.in_([ChatType.GROUP, ChatType.SUPERGROUP]))
async def handle_group_message(message: types.Message):

    if not hasattr(handle_group_message, "prevmsg"):
        prevmsg = -1

    # Логируем все сообщения
    logger.info(
        f"Группа '{message.chat.title}': {message.message_id} ({message.media_group_id}) -> {message.from_user.first_name} -> {message.text} -> {message.caption}"
    )
    if message.forward_from_chat:

        logger.info(f"{message.media_group_id}, {prevmsg}")
        if message.media_group_id != prevmsg:
            if message.media_group_id:
                prevmsg = message.media_group_id
            await set_reaction_with_retry(message.chat.id, message.message_id)
            if message.content_type != types.ContentType.PHOTO or message.caption:
                comment = random.choice(comments)
                if callable(comment):
                    comm = comment()
                else:
                    comm = comment
                await message.reply(comm)
            else:
                comment = random.choice(ph_comments)
                if callable(comment):
                    comm = comment()
                else:
                    comm = comment
                await message.reply(comm)
        else:
            logger.info("skip")
    else:
        for key in banwords.keys():
            if re.search(key, message.text, re.IGNORECASE | re.MULTILINE):
                await message.reply(banwords.get(key, "нельзя"))


@dp.message(Command("/stats"))
async def count_posts(message: types.Message):
    await message.reply("123")


async def main():
    logger.info("Бот запущен...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(e)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("бот остановлен")
