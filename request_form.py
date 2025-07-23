from aiogram import Router, types, Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import Message
from email_utils import send_request_email

request_router = Router()

class RequestForm(StatesGroup):
    full_name = State()
    description = State()


@request_router.message(Command("request"))
async def start_request(message: Message, state: FSMContext):
    await message.answer("Введите ваше ФИО. Чтобы выйти из процесса создания заявки и вернуть в чат с поддержкой -- нажмите /start")
    await state.set_state(RequestForm.full_name)


@request_router.message(RequestForm.full_name)
async def get_full_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("Теперь опишите суть обращения. Чтобы выйти из процесса создания заявки и вернуть в чат с поддержкой -- нажмите /start")
    await state.set_state(RequestForm.description)


@request_router.message(RequestForm.description)
async def get_description_and_send(message: Message, state: FSMContext):
    data = await state.get_data()
    full_name = data["full_name"]
    description = message.text

    success = send_request_email(subject=full_name, body=description)

    if success:
        await message.answer("✅ Заявка успешно отправлена в службу поддержки.")
    else:
        await message.answer("❌ Не удалось отправить заявку. Попробуйте позже.")

    await state.clear()
