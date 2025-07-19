# handlers/manager.py

from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from middlewares.role_middleware import RoleMiddleware

router = Router()

# Применяем RoleMiddleware к роутеру менеджера
router.message.middleware(RoleMiddleware(required_roles=['admin', 'manager']))
router.callback_query.middleware(RoleMiddleware(required_roles=['admin', 'manager']))



@router.message(Command("my_orders"))
async def cmd_my_orders(message: Message, user_role: str):
    """
    Обработчик команды /my_orders.
    """
    await message.answer(f"Вы {user_role}. Показываю ваши заказы...")
    # Здесь будет логика для отображения заказов пользователя

@router.message(Command("sales_manager"))
async def cmd_sales_manager(message: Message, user_role: str):
    """
    Обработчик команды /sales_manager.
    """
    await message.answer(f"Вы {user_role}. Формирую отчет по продажам менеджеров...")
    # Здесь будет логика для формирования отчета по продажам менеджеров