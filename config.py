import csv
import os
from aiogram.types import BotCommand

# Текст приветствия
WELCOME_MESSAGE = "добро пожаловать! Задайте свой вопрос, и мы скоро ответим."

# Служебные фразы (если используешь)
REPLY_TO_THIS_MESSAGE = "REPLY_TO_THIS"
WRONG_REPLY = "WRONG_REPLY"

# Карты соответствий (в памяти, временные)
USER_TOPICS = {}  # user_id: thread_id
TOPIC_USERS = {}  # thread_id: user_id

# --- Пути и хранилище ---

USER_CSV_PATH = "users.csv"  # CSV-файл для хранения соответствий

# Словари соответствий (в памяти)
USER_TOPICS = {}  # user_id: thread_id
TOPIC_USERS = {}  # thread_id: user_id

# --- Загрузка соответствий из CSV ---

if os.path.exists(USER_CSV_PATH):
    with open(USER_CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # Пропустить заголовок (если есть)
        for row in reader:
            if len(row) != 2:
                continue
            user_id, thread_id = row
            try:
                user_id = int(user_id)
                thread_id = int(thread_id)
                USER_TOPICS[user_id] = thread_id
                TOPIC_USERS[thread_id] = user_id
            except ValueError:
                continue

# --- Функция добавления новой пары user_id <-> thread_id ---

def add_user_thread_mapping(user_id: int, thread_id: int):
    if user_id not in USER_TOPICS:
        USER_TOPICS[user_id] = thread_id
        TOPIC_USERS[thread_id] = user_id
        with open(USER_CSV_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([user_id, thread_id])


# Команды
commands = [
    BotCommand(command="start", description="Начало работы/Сброс"),
    BotCommand(command="request", description="Создать заявку в службу поддержки"),               
]