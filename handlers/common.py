# handlers/common.py
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart, Command

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    """
    Обработчик команды /start.
    """
    await message.answer("Привет! Я ваш мини-CRM бот. Используйте меню для навигации.")

@router.message(Command("help"))
async def cmd_help(message: Message):
    """
    Обработчик команды /help.
    """
    await message.answer("Я мини-CRM бот. Могу помочь с заказами, складом, оплатами и отчетами. "
                         "Используйте команды из меню.")