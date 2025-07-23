import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from handlers import main_router, start_router
from config import commands
from my_secrets import TELEGRAM_TOKEN
from request_form import request_router


logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_TOKEN)

async def main():
    bot = Bot(token=TELEGRAM_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start_router)
    dp.include_router(request_router)
    dp.include_router(main_router)
    await bot.set_my_commands(commands)

    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
