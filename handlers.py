import logging
import html
from typing import Optional
from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram import F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

from config import WELCOME_MESSAGE, USER_TOPICS, TOPIC_USERS, add_user_thread_mapping
from my_secrets import TELEGRAM_SUPPORT_CHAT_ID
from storage import (
    add_duty,
    close_ticket,
    create_ticket,
    get_open_ticket_by_user,
    get_ticket_by_topic,
    increment_message_count,
    list_duty_staff,
    remove_duty,
    set_rating,
    stats_summary,
    set_setting,
    get_setting,
    get_ticket_by_id,
    reset_stats,
    all_ticket_topics,
    user_ticket_count,
)

main_router = Router()
start_router = Router()
pending_ratings = {}  # user_id -> ticket_id

# Клавиатура с основными командами для саппорт-группы (тема General)
SUPPORT_MENU_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👥 Дежурные (панель)"), KeyboardButton(text="📋 Дежурные (список)")],
        [KeyboardButton(text="📊 Отправить статистику"), KeyboardButton(text="📌 Привязать тему статистики")],
        [KeyboardButton(text="👋 Стать дежурным"), KeyboardButton(text="🚪 Выйти из дежурных")],
        [KeyboardButton(text="✅ Кнопка закрытия"), KeyboardButton(text="ℹ️ Помощь")],
        [KeyboardButton(text="♻️ Сброс статистики"), KeyboardButton(text="🧹 Удалить треды")],
    ],
    resize_keyboard=True,
)


class DutyAdd(StatesGroup):
    waiting_username = State()

@start_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(f"{message.from_user.first_name}, {WELCOME_MESSAGE}")


@main_router.message(lambda m: m.chat.type == "private")
async def handle_user_message(message: Message, bot: Bot):
    user_id = message.from_user.id
    text = message.text or message.caption or ""

    # Пользователь оценивает закрытую заявку
    if (
        text
        and text.isdigit()
        and int(text) in (1, 3, 5)
        and user_id in pending_ratings
    ):
        rating = int(text)
        ticket_id = pending_ratings.pop(user_id)
        set_rating(ticket_id, rating)
        ticket = get_ticket_by_id(ticket_id)
        if ticket:
            try:
                await bot.send_message(
                    chat_id=TELEGRAM_SUPPORT_CHAT_ID,
                    message_thread_id=ticket["topic_id"],
                    text=f"Пользователь оценил заявку #{ticket_id} на {rating}/5",
                )
            except Exception:
                logging.exception("Не удалось отправить сообщение об оценке в тред")
        await message.answer(
            f"Спасибо! Оценка {rating} сохранена.",
            reply_markup=ReplyKeyboardRemove(),
        )
        logging.info(f"Saved rating {rating} for ticket {ticket_id}")
        return

    username = message.from_user.username or ""
    full_name = message.from_user.full_name or username or f"User_{user_id}"

    # Ищем открытую заявку пользователя
    ticket = get_open_ticket_by_user(user_id)

    if ticket is None:
        # Формируем название темы по тексту обращения
        def make_topic_title() -> str:
            base = text.strip().replace("\n", " ")
            if not base:
                base = message.content_type
            # Ограничение Telegram на длину названия темы — 128 символов
            base = base[:96].rstrip()
            return f"{base} — {full_name}" if base else f"Заявка — {full_name}"

        try:
            topic = await bot.create_forum_topic(
                chat_id=TELEGRAM_SUPPORT_CHAT_ID,
                name=make_topic_title(),
            )
            topic_id = topic.message_thread_id
        except TelegramBadRequest as e:
            await message.answer(
                "Пока не можем принять обращение: у бота нет права создавать темы в группе. "
                "Дайте боту админ‑права с разрешением на темы и повторите."
            )
            logging.exception("Не удалось создать тему в группе")
            return
        ticket_id = create_ticket(
            user_id=user_id,
            username=username,
            full_name=full_name,
            topic_id=topic_id,
            first_message=text or message.content_type,
        )
        add_user_thread_mapping(user_id, topic_id)
        duty_mentions = " ".join(f"@{u}" for u in list_duty_staff()) or "Дежурные не заданы."
        user_link = (
            f"@{username}"
            if username
            else f"<a href=\"tg://user?id={user_id}\">{html.escape(full_name)}</a>"
        )
        try:
            await bot.send_message(
                chat_id=TELEGRAM_SUPPORT_CHAT_ID,
                text=(
                    f"Новая заявка #{ticket_id} от {html.escape(full_name)} "
                    f"(id: {user_id}, {user_link}).\n{duty_mentions}"
                ),
                message_thread_id=topic_id,
                parse_mode="HTML",
            )
            await bot.send_message(
                chat_id=TELEGRAM_SUPPORT_CHAT_ID,
                text=f"Управление заявкой #{ticket_id}",
                message_thread_id=topic_id,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="✅ Закрыть заявку",
                                callback_data=f"close:{ticket_id}",
                            )
                        ]
                    ]
                ),
            )
        except Exception:
            logging.exception("Не удалось отправить сообщение с кнопкой закрытия")
    else:
        topic_id = ticket["topic_id"]
        ticket_id = ticket["id"]
        add_user_thread_mapping(user_id, topic_id)
        increment_message_count(ticket_id)

    # Пересылаем сообщение в тред заявки
    await bot.forward_message(
        chat_id=TELEGRAM_SUPPORT_CHAT_ID,
        from_chat_id=message.chat.id,
        message_id=message.message_id,
        message_thread_id=topic_id,
    )

    await message.answer(
        f"Ваше сообщение отправлено в поддержку. Всего ваших обращений: {user_ticket_count(user_id)}."
    )
    logging.info(f"Forwarded message from user {user_id} to thread {topic_id} (ticket {ticket_id})")


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
    ticket = get_ticket_by_topic(thread_id)
    ticket_id = ticket["id"] if ticket else None
    if ticket and not user_id:
        user_id = ticket["user_id"]
        add_user_thread_mapping(user_id, thread_id)

    if not user_id or not ticket_id:
        await message.reply("Не удалось определить пользователя для этого треда.")
        return

    # Закрытие заявки из треда
    if message.text and message.text.startswith("/close"):
        close_ticket(ticket_id)
        pending_ratings[user_id] = ticket_id
        await message.reply(f"Заявка #{ticket_id} закрыта. Запросите у пользователя оценку.")
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=str(i)) for i in (1, 3, 5)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await bot.send_message(
            chat_id=user_id,
            text=f"Ваша заявка #{ticket_id} закрыта. Оцените работу поддержки от 1 до 5:",
            reply_markup=kb,
        )
        await close_forum_thread(bot, thread_id)
        await send_stats_snapshot(bot)
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

        logging.info(f"Sent reply to user {user_id} from thread {thread_id} (ticket {ticket_id})")

    except Exception as e:
        logging.exception("Ошибка при отправке сообщения пользователю")
        await message.reply(f"Ошибка при отправке пользователю: {e}")


@main_router.message(Command("stats"))
async def stats(message: Message):
    if message.chat.id != TELEGRAM_SUPPORT_CHAT_ID:
        return
    data = stats_summary()
    top = "\n".join(
        f"- {row['username'] or row['user_id']}: {row['cnt']} обращений"
        for row in data["top_users"]
    ) or "нет данных"
    avg = f"{data['avg_rating']:.2f}" if data["avg_rating"] is not None else "нет оценок"
    text = (
        f"Статистика обращений:\n"
        f"Всего: {data['total']}\n"
        f"Открыто: {data['open']}\n"
        f"Закрыто: {data['closed']}\n"
        f"Средняя оценка: {avg}\n"
        f"Топ пользователей:\n{top}"
    )
    await message.reply(text)


@main_router.message(Command("help"))
async def help_cmd(message: Message):
    if message.chat.id != TELEGRAM_SUPPORT_CHAT_ID:
        return
    await message.reply(
        "Меню саппорта:\n"
        "👥 Дежурные (панель) — открыть панель управления дежурными\n"
        "📋 Дежурные (список) — показать список дежурных\n"
        "📊 Отправить статистику — отправить статистику в выбранную тему\n"
        "📌 Привязать тему статистики — сохранить текущий тред как канал для статистики\n"
        "✅ Кнопка закрытия — вывести кнопку закрытия заявки в текущем треде\n"
        "ℹ️ Помощь — эта подсказка\n",
        reply_markup=SUPPORT_MENU_KB,
    )


async def ensure_stats_topic(bot: Bot) -> int:
    """Create 'Статистика' topic if not set; return topic_id."""
    topic = get_setting("stats_topic_id")
    if topic:
        return int(topic)
    try:
        created = await bot.create_forum_topic(
            chat_id=TELEGRAM_SUPPORT_CHAT_ID,
            name="Статистика",
        )
        set_setting("stats_topic_id", str(created.message_thread_id))
        return created.message_thread_id
    except Exception as e:
        logging.exception("Не удалось создать тему 'Статистика'")
        raise TelegramBadRequest("not enough rights to create a topic") from e


@main_router.message(Command("stats_set"))
async def stats_set(message: Message):
    if message.chat.id != TELEGRAM_SUPPORT_CHAT_ID or not message.is_topic_message:
        await message.reply("Команда выполняется внутри темы саппорт-чата.")
        return
    set_setting("stats_topic_id", str(message.message_thread_id))
    await message.reply("Эта тема сохранена как канал для публикации статистики.")


@main_router.message(Command("stats_post"))
async def stats_post(message: Message, bot: Bot):
    if message.chat.id != TELEGRAM_SUPPORT_CHAT_ID:
        return
    await send_stats_snapshot(bot, message)


async def send_stats_snapshot(bot: Bot, message: Optional[Message] = None):
    """Отправить статистику в сохранённый тред."""
    topic = get_setting("stats_topic_id")
    if not topic:
        try:
            topic = await ensure_stats_topic(bot)
            if message and not message.is_topic_message:
                await message.reply("Создал тему 'Статистика' и публикую туда.")
        except TelegramBadRequest:
            if message:
                await message.reply(
                    "Не удалось создать тему 'Статистика': нет прав создавать темы. "
                    "Сделайте бота админом с правом на темы или создайте тему вручную и выполните /stats_set в ней."
                )
            return
    data = stats_summary()
    top = "\n".join(
        f"- {row['username'] or row['user_id']}: {row['cnt']} обращений"
        for row in data["top_users"]
    ) or "нет данных"
    avg = f"{data['avg_rating']:.2f}" if data["avg_rating"] is not None else "нет оценок"
    text = (
        f"Статистика обращений:\n"
        f"Всего: {data['total']}\n"
        f"Открыто: {data['open']}\n"
        f"Закрыто: {data['closed']}\n"
        f"Средняя оценка: {avg}\n"
        f"Топ пользователей:\n{top}"
    )
    await bot.send_message(
        chat_id=TELEGRAM_SUPPORT_CHAT_ID,
        message_thread_id=int(topic),
        text=text,
    )
    if message and not message.is_topic_message:
        await message.reply("Статистика отправлена в выбранную тему.")


async def close_forum_thread(bot: Bot, topic_id: int):
    """Закрыть форумный тред (добавит замочек в Telegram)."""
    try:
        await bot.close_forum_topic(chat_id=TELEGRAM_SUPPORT_CHAT_ID, message_thread_id=topic_id)
    except Exception:
        logging.exception("Не удалось закрыть форумный тред %s", topic_id)


# --- Обработка кнопочного меню (текстовые кнопки) ---

@main_router.message(F.text == "👥 Дежурные (панель)")
async def menu_duty_panel(message: Message, state: FSMContext):
    await duty_panel(message, state)


@main_router.message(F.text == "📋 Дежурные (список)")
async def menu_duty_list(message: Message):
    await duty_list(message)


@main_router.message(F.text == "📊 Отправить статистику")
async def menu_stats_post(message: Message, bot: Bot):
    await stats_post(message, bot)


@main_router.message(F.text == "📌 Привязать тему статистики")
async def menu_stats_set(message: Message):
    await stats_set(message)


@main_router.message(F.text == "✅ Кнопка закрытия")
async def menu_close_btn(message: Message):
    await send_close_button(message)


@main_router.message(F.text == "ℹ️ Помощь")
async def menu_help(message: Message):
    await help_cmd(message)


@main_router.message(F.text == "👋 Стать дежурным")
@main_router.message(Command("duty_me_on"))
async def duty_me_on(message: Message):
    if message.chat.id != TELEGRAM_SUPPORT_CHAT_ID:
        return
    username = (message.from_user.username or "").strip()
    if not username:
        await message.reply("У вас нет username. Задайте его в Telegram и повторите.")
        return
    add_duty(username)
    await message.reply(f"@{username} добавлен в дежурные.", reply_markup=duty_keyboard())


@main_router.message(F.text == "🚪 Выйти из дежурных")
@main_router.message(Command("duty_me_off"))
async def duty_me_off(message: Message):
    if message.chat.id != TELEGRAM_SUPPORT_CHAT_ID:
        return
    username = (message.from_user.username or "").strip()
    if not username:
        await message.reply("У вас нет username. Задайте его в Telegram и повторите.")
        return
    remove_duty(username)
    await message.reply(f"@{username} исключён из дежурных.", reply_markup=duty_keyboard())


@main_router.message(F.text == "♻️ Сброс статистики")
@main_router.message(Command("reset_stats"))
async def reset_stats_cmd(message: Message):
    if message.chat.id != TELEGRAM_SUPPORT_CHAT_ID:
        return
    if message.from_user.id != 247880158:
        await message.reply("Эта команда доступна только администратору.")
        return
    reset_stats()
    await message.reply("Статистика и заявки обнулены.")


@main_router.message(F.text == "🧹 Удалить треды")
@main_router.message(Command("purge_topics"))
async def purge_topics(message: Message, bot: Bot):
    if message.chat.id != TELEGRAM_SUPPORT_CHAT_ID:
        return
    if message.from_user.id != 247880158:
        await message.reply("Эта команда доступна только администратору.")
        return
    stats_topic = get_setting("stats_topic_id")
    deleted = 0
    failed = 0
    topics = all_ticket_topics()
    for topic_id in topics:
        if stats_topic and int(stats_topic) == int(topic_id):
            continue
        try:
            await bot.delete_forum_topic(
                chat_id=TELEGRAM_SUPPORT_CHAT_ID, message_thread_id=topic_id
            )
            deleted += 1
        except Exception:
            failed += 1
            logging.exception("Не удалось удалить тред %s", topic_id)
    # Чистим заявки после удаления тредов
    reset_stats()
    await message.reply(
        f"Удалено тредов: {deleted}. Ошибок: {failed}. "
        f"Статистический тред сохранён. Заявки/статистика обнулены."
    )


def duty_keyboard() -> InlineKeyboardMarkup:
    staff = list_duty_staff()
    rows = [
        [
            InlineKeyboardButton(
                text=f"❌ {u}",
                callback_data=f"duty_del:{u}",
            )
        ]
        for u in staff
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить", callback_data="duty_add")])
    return InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text="➕ Добавить", callback_data="duty_add")]])


@main_router.message(Command("duty_panel"))
async def duty_panel(message: Message, state: FSMContext):
    if message.chat.id != TELEGRAM_SUPPORT_CHAT_ID:
        return
    await state.clear()
    staff = list_duty_staff()
    text = "Дежурные: " + (", ".join(f"@{u}" for u in staff) if staff else "нет")
    await message.reply(text, reply_markup=duty_keyboard())


@main_router.callback_query(F.data == "duty_add")
async def duty_add_start(callback: CallbackQuery, state: FSMContext):
    if callback.message.chat.id != TELEGRAM_SUPPORT_CHAT_ID:
        await callback.answer()
        return
    await state.set_state(DutyAdd.waiting_username)
    await callback.answer("Введите @username дежурного сообщением в чат.")
    await callback.message.reply("Напишите @username, которого нужно добавить в дежурные.")


@main_router.message(DutyAdd.waiting_username)
async def duty_add_wait_username(message: Message, state: FSMContext):
    if message.chat.id != TELEGRAM_SUPPORT_CHAT_ID:
        return
    username = message.text.strip().lstrip("@")
    if not username:
        await message.reply("Укажите username в формате @user.")
        return
    add_duty(username)
    await state.clear()
    await message.reply(f"@{username} добавлен в дежурные.", reply_markup=duty_keyboard())


@main_router.callback_query(F.data.startswith("duty_del:"))
async def duty_delete(callback: CallbackQuery):
    if callback.message.chat.id != TELEGRAM_SUPPORT_CHAT_ID:
        await callback.answer()
        return
    username = callback.data.split(":", 1)[1]
    remove_duty(username)
    await callback.answer(f"@{username} удалён")
    try:
        await callback.message.edit_reply_markup(reply_markup=duty_keyboard())
    except Exception:
        pass


@main_router.message(Command("close_btn"))
async def send_close_button(message: Message):
    """Ручная команда: отправить кнопку закрытия в текущий тред."""
    if message.chat.id != TELEGRAM_SUPPORT_CHAT_ID or not message.is_topic_message:
        await message.reply("Команда работает только внутри треда саппорта.")
        return
    ticket = get_ticket_by_topic(message.message_thread_id)
    if not ticket:
        await message.reply("Для этого треда заявка не найдена.")
        return
    ticket_id = ticket["id"]
    await message.reply(
        f"Заявка #{ticket_id}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Закрыть заявку", callback_data=f"close:{ticket_id}"
                    )
                ]
            ]
        ),
    )


@main_router.callback_query(F.data.startswith("close:"))
async def close_via_button(callback: CallbackQuery, bot: Bot):
    if callback.message.chat.id != TELEGRAM_SUPPORT_CHAT_ID or not callback.message.is_topic_message:
        await callback.answer("Можно закрывать только в саппорт-треде.")
        return
    try:
        ticket_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректный ticket id.")
        return
    ticket = get_ticket_by_topic(callback.message.message_thread_id)
    if not ticket or ticket["id"] != ticket_id:
        await callback.answer("Заявка не найдена для этого треда.")
        return
    user_id = ticket["user_id"]
    close_ticket(ticket_id)
    pending_ratings[user_id] = ticket_id
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=str(i)) for i in (1, 3, 5)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await bot.send_message(
        chat_id=user_id,
        text=f"Ваша заявка #{ticket_id} закрыта. Оцените работу поддержки от 1 до 5:",
        reply_markup=kb,
    )
    await close_forum_thread(bot, callback.message.message_thread_id)
    await send_stats_snapshot(bot)
    await callback.answer("Заявка закрыта, запросили оценку у пользователя.")
    await callback.message.reply(f"Заявка #{ticket_id} закрыта.")


@main_router.message(Command("duty_list"))
async def duty_list(message: Message):
    if message.chat.id != TELEGRAM_SUPPORT_CHAT_ID:
        return
    staff = list_duty_staff()
    if not staff:
        await message.reply("Дежурные не заданы.")
    else:
        await message.reply("Дежурные: " + ", ".join(f"@{u}" for u in staff))


@main_router.message(Command("duty_add"))
async def duty_add(message: Message):
    if message.chat.id != TELEGRAM_SUPPORT_CHAT_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Используйте: /duty_add @username")
        return
    username = parts[1]
    add_duty(username)
    await message.reply(f"@{username.lstrip('@')} добавлен в дежурные.")


@main_router.message(Command("duty_remove"))
async def duty_remove_cmd(message: Message):
    if message.chat.id != TELEGRAM_SUPPORT_CHAT_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Используйте: /duty_remove @username")
        return
    username = parts[1]
    remove_duty(username)
    await message.reply(f"@{username.lstrip('@')} удалён из дежурных.")
