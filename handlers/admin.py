# handlers/admin.py
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from middlewares.role_middleware import RoleMiddleware

router = Router()

# Применяем RoleMiddleware для админских команд
router.message.middleware(RoleMiddleware(required_roles=['admin']))
router.callback_query.middleware(RoleMiddleware(required_roles=['admin']))


@router.message(Command("edit_order_admin"))
async def cmd_edit_order_admin(message: Message, user_role: str):
    """
    Обработчик команды /edit_order_admin.
    """
    await message.answer(f"Вы {user_role}. Запуск процесса редактирования заказа (админ)...")
    # Здесь будет FSM для редактирования заказа админом

@router.message(Command("show_unconfirmed_orders"))
async def cmd_show_unconfirmed_orders(message: Message, user_role: str):
    """
    Обработчик команды /show_unconfirmed_orders.
    """
    await message.answer(f"Вы {user_role}. Показываю черновики заказов для подтверждения...")
    # Здесь будет логика для отображения неподтвержденных заказов