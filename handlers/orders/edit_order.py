# handlers/orders/edit_order.py (ГЛАВНЫЙ ФАЙЛ МОДУЛЯ РЕДАКТИРОВАНИЯ ЗАКАЗОВ)

import datetime
import logging
from decimal import Decimal

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from middlewares.role_middleware import RoleMiddleware
from db.setup import get_db_session
from db.models import Order, Client, Employee, Address, OrderLine, Product # Убедитесь, что все эти модели импортированы
from sqlalchemy.future import select
from sqlalchemy import delete
from sqlalchemy.orm import selectinload
from utils.text_formatter import escape_markdown_v2, bold, italic
from states.order_states import OrderEditingStates

# ✅ ИМПОРТИРУЕМ ОБЩИЕ СЕРВИСНЫЕ ФУНКЦИИ ИЗ НОВОГО ФАЙЛА
from services.order_editing_service import process_my_order_selection, return_to_order_menu

# ✅ ИМПОРТИРУЕМ РОУТЕРЫ ИЗ НОВЫХ ПОД-МОДУЛЕЙ
from .order_editing import change_quantity
from .order_editing import add_product
from .order_editing import change_date
from .order_editing import delete_product
from .order_editing import delete_order


router = Router()

router.message.middleware(RoleMiddleware(required_roles=['admin', 'manager']))
router.callback_query.middleware(RoleMiddleware(required_roles=['admin', 'manager']))

# ✅ ВКЛЮЧАЕМ РОУТЕРЫ ИЗ НОВЫХ ФАЙЛОВ В ГЛАВНЫЙ РОУТЕР
router.include_router(change_quantity.router)
router.include_router(add_product.router)
router.include_router(change_date.router)
router.include_router(delete_product.router)
router.include_router(delete_order.router)


@router.message(Command("my_orders"))
async def cmd_my_orders(message: Message, state: FSMContext, user_role: str, db_user: Employee):
    """
    Показывает список заказов текущего менеджера со статусом 'draft' или 'pending' для редактирования.
    """
    await message.answer(f"Вы {user_role}. Загружаю ваши неподтвержденные заказы.")

    async for session in get_db_session():
        orders_stmt = select(Order).where(
            Order.employee_id == db_user.employee_id,
            Order.status.in_(['draft', 'pending'])
        ).order_by(Order.order_date.desc())

        orders_result = await session.execute(orders_stmt)
        orders = orders_result.scalars().all()

        if not orders:
            await message.answer("У вас нет активных (черновиков или ожидающих) заказов для редактирования.")
            await state.clear()
            return

        buttons = []
        for order in orders:
            client_name = "Неизвестный клиент"
            if order.client_id:
                client_stmt = select(Client).where(Client.client_id == order.client_id)
                client_result = await session.execute(client_stmt)
                client = client_result.scalar_one_or_none()
                if client:
                    client_name = client.name

            button_text = escape_markdown_v2(
                f"№{order.order_id} | {client_name} | {order.order_date.strftime('%d.%m.%Y')} | {round(order.total_amount, 2)} грн | {order.status}"
            )
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"edit_order_select_{order.order_id}")])

        buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order_editing")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer("Выберите заказ для редактирования:", reply_markup=keyboard, parse_mode="MarkdownV2")
        await state.set_state(OrderEditingStates.waiting_for_my_order_selection)


# ✅ НОВЫЙ ХЭНДЛЕР: Обработка выбора заказа (для решения Проблемы 2)
@router.callback_query(OrderEditingStates.waiting_for_my_order_selection, F.data.startswith("edit_order_select_"))
async def handle_order_selection_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Хэндлер, который перехватывает выбор заказа и вызывает сервисную функцию process_my_order_selection.
    """
    await process_my_order_selection(callback, state, bot)

# Хэндлер для отмены редактирования (CallbackQuery handler)
@router.callback_query(F.data == "cancel_order_editing")
async def cancel_order_editing(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await bot(callback.message.edit_text(f"{bold('❌ Редактирование заказа отменено.')}", parse_mode="MarkdownV2"))
    await bot(callback.answer())


# Хэндлер для кнопки "Готово" (пока просто очистка состояния) (CallbackQuery handler)
@router.callback_query(OrderEditingStates.my_order_menu, F.data == "done_editing_order")
async def done_editing_order(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await bot(callback.message.edit_text(f"{bold('✅ Редактирование завершено. Возвращаюсь в главное меню.')}", parse_mode="MarkdownV2"))
    await bot(callback.answer())

# Все остальные хэндлеры (delete_order_confirm, delete_order_final_yes, delete_order_final_no,
# edit_item_quantity_start, process_item_to_edit_quantity, process_new_quantity,
# process_new_quantity_invalid, cancel_item_quantity_edit, edit_delivery_date_start,
# process_new_delivery_date_selection, cancel_delivery_date_edit, add_item_to_order_start)
# БЫЛИ ПЕРЕМЕЩЕНЫ В СООТВЕТСТВУЮЩИЕ ФАЙЛЫ В order_editing/