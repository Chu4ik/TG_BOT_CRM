# handlers/manager.py

import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from middlewares.role_middleware import RoleMiddleware
from db.setup import get_db_session
from db.models import Order, OrderLine, Client, Employee, Address
from sqlalchemy.future import select
from sqlalchemy import delete
from utils.text_formatter import escape_markdown_v2, bold, italic
from states.order_states import OrderEditingStates # Импортируем новый класс состояний

router = Router()

# Менеджеры и админы могут просматривать и редактировать свои заказы
router.message.middleware(RoleMiddleware(required_roles=['admin', 'manager']))
router.callback_query.middleware(RoleMiddleware(required_roles=['admin', 'manager']))


@router.message(Command("sales_manager"))
async def cmd_sales_manager(message: Message, user_role: str):
    """
    Обработчик команды /sales_manager.
    """
    await message.answer(f"Вы {user_role}. Формирую отчет по продажам менеджеров...")
    # Здесь будет логика для формирования отчета по продажам менеджеров