# handlers/orders/add_datedeliveries_order.py

from aiogram import Router
from middlewares.role_middleware import RoleMiddleware # Импортируем RoleMiddleware

router = Router() # <--- ОБЯЗАТЕЛЬНО: Определение роутера

# Здесь можно добавить middlewares для этого роутера, если они нужны
# router.message.middleware(RoleMiddleware(required_roles=['admin', 'manager']))
# router.callback_query.middleware(RoleMiddleware(required_roles=['admin', 'manager']))

# Пример заглушки для будущего хэндлера
# @router.callback_query(OrderCreationStates.waiting_for_delivery_date, F.data.startswith("select_delivery_date_"))
# async def process_delivery_date_selection(callback: CallbackQuery, state: FSMContext):
#     await callback.message.edit_text("Дата доставки выбрана (заглушка).")
#     await callback.answer()
#     # Здесь будет логика для обработки выбора даты доставки
#     # Затем переход к следующему шагу или завершение