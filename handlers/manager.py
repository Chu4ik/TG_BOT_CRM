# handlers/manager.py
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from middlewares.role_middleware import RoleMiddleware # Импортируем RoleMiddleware

router = Router()

# Применяем RoleMiddleware к роутеру менеджера
# Это означает, что все хэндлеры в этом роутере будут проходить через проверку роли
# Если вы хотите более гранулированный контроль, применяйте middleware к отдельным хэндлерам
router.message.middleware(RoleMiddleware(required_roles=['admin', 'manager']))
router.callback_query.middleware(RoleMiddleware(required_roles=['admin', 'manager']))


@router.message(Command("new_order"))
async def cmd_new_order(message: Message, user_role: str):
    """
    Обработчик команды /new_order.
    """
    await message.answer(f"Вы {user_role}. Запуск процесса создания нового заказа...")
    # Здесь будет FSM для создания заказа

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