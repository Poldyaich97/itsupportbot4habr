from aiogram.types import BotCommand

# Текст приветствия
WELCOME_MESSAGE = "добро пожаловать! Задайте свой вопрос, и мы скоро ответим."

# Карты соответствий (в памяти, временные)
USER_TOPICS = {}  # user_id: thread_id
TOPIC_USERS = {}  # thread_id: user_id


def add_user_thread_mapping(user_id: int, thread_id: int):
    USER_TOPICS[user_id] = thread_id
    TOPIC_USERS[thread_id] = user_id


# Команды, показываемые пользователю
commands = []
