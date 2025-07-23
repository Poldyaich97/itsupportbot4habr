from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message
from config import WELCOME_MESSAGE, USER_TOPICS, TOPIC_USERS, add_user_thread_mapping
from my_secrets import TELEGRAM_SUPPORT_CHAT_ID
from aiogram.fsm.context import FSMContext

import logging

main_router = Router()
start_router = Router()

@start_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(f"{message.from_user.first_name}, {WELCOME_MESSAGE}")


@main_router.message(lambda m: m.chat.type == "private")
async def handle_user_message(message: Message, bot: Bot):
    user_id = message.from_user.id

    # Проверка: есть ли уже тема для пользователя
    topic_id = USER_TOPICS.get(user_id)

    if topic_id is None:
        # Создаем новую тему в супергруппе
        username = message.from_user.full_name or message.from_user.username or f"User_{user_id}"
        topic = await bot.create_forum_topic(
            chat_id=TELEGRAM_SUPPORT_CHAT_ID,
            name=f"{username}",
        )
        topic_id = topic.message_thread_id
        add_user_thread_mapping(user_id, topic_id)

    # Пересылаем сообщение в нужный тред
    await bot.forward_message(
        chat_id=TELEGRAM_SUPPORT_CHAT_ID,
        from_chat_id=message.chat.id,
        message_id=message.message_id,
        message_thread_id=topic_id,
    )

    await message.answer("Ваше сообщение отправлено в поддержку. Ожидайте ответа.")
    logging.info(f"Forwarded message from user {user_id} to thread {topic_id}")


@main_router.message(lambda m: m.chat.id == TELEGRAM_SUPPORT_CHAT_ID and m.is_topic_message)
async def handle_support_reply(message: Message, bot: Bot):
    # Игнорируем пересланные сообщения
    if message.forward_from or message.forward_from_chat:
        return

    # Игнорируем пустые апдейты (например, при переименовании треда)
    if not any([message.text, message.photo, message.document, message.video, message.video_note, message.sticker, message.audio, message.voice]):
        return
    
    # Если сообщение от самого бота — игнорируем
    if message.from_user.is_bot:
        return

    thread_id = message.message_thread_id
    user_id = TOPIC_USERS.get(thread_id)

    if not user_id:
        await message.reply("Не удалось определить пользователя для этого треда.")
        return

    try:
        # Текст
        if message.text:
            await bot.send_message(chat_id=user_id, text=f"IT Support: {message.text}")

        # Фото
        elif message.photo:
            caption = f"IT Support: {message.caption or ''}"
            await bot.send_photo(chat_id=user_id, photo=message.photo[-1].file_id, caption=caption)

        # Документ
        elif message.document:
            caption = f"IT Support: {message.caption or ''}"
            await bot.send_document(chat_id=user_id, document=message.document.file_id, caption=caption)

        # Видео
        elif message.video:
            caption = f"IT Support: {message.caption or ''}"
            await bot.send_video(chat_id=user_id, video=message.video.file_id, caption=caption)

        # Стикер
        elif message.sticker:
            await bot.send_sticker(chat_id=user_id, sticker=message.sticker.file_id)

        # Голосовые
        elif message.voice:
            await bot.send_voice(chat_id=user_id, voice=message.voice.file_id)

        # Видео-сообщение (кружочек)
        elif message.video_note:
            await bot.send_video_note(chat_id=user_id, video_note=message.video_note.file_id)

        # Аудио
        elif message.audio:
            await bot.send_audio(chat_id=user_id, audio=message.audio.file_id, caption=message.caption or "")

        else:
            await bot.send_message(chat_id=user_id, text="IT Support: [Неподдерживаемый тип сообщения]")

        logging.info(f"Sent reply to user {user_id} from thread {thread_id}")

    except Exception as e:
        logging.exception("Ошибка при отправке сообщения пользователю")
        await message.reply(f"Ошибка при отправке пользователю: {e}")
