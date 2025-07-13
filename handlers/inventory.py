# handlers/inventory.py
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from middlewares.role_middleware import RoleMiddleware

router = Router()

# Применяем RoleMiddleware для команд склада (доступно админам и, возможно, менеджерам)
router.message.middleware(RoleMiddleware(required_roles=['admin', 'manager']))
router.callback_query.middleware(RoleMiddleware(required_roles=['admin', 'manager']))


@router.message(Command("add_delivery"))
async def cmd_add_delivery(message: Message, user_role: str):
    """
    Обработчик команды /add_delivery.
    """
    await message.answer(f"Вы {user_role}. Запуск процесса добавления поступления товара...")
    # Здесь будет FSM для добавления поступления

@router.message(Command("adjust_inventory"))
async def cmd_adjust_inventory(message: Message, user_role: str):
    """
    Обработчик команды /adjust_inventory.
    """
    await message.answer(f"Вы {user_role}. Запуск процесса корректировки по складу...")
    # Здесь будет FSM для корректировки

@router.message(Command("inventory_report"))
async def cmd_inventory_report(message: Message, user_role: str):
    """
    Обработчик команды /inventory_report.
    """
    await message.answer(f"Вы {user_role}. Формирую отчет об остатках товара...")
    # Здесь будет логика для отчета по складу