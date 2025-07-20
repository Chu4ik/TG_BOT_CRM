# handlers/orders/order_editing/change_date.py (внутри process_new_delivery_date_selection)

import datetime
import logging

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from middlewares.role_middleware import RoleMiddleware
from db.setup import get_db_session
from db.models import Order
from sqlalchemy.future import select
from utils.text_formatter import escape_markdown_v2, bold, italic
from states.order_states import OrderEditingStates

# Импортируем функцию для возврата в меню редактирования из общего сервисного файла
from services.order_editing_service import process_my_order_selection, return_to_order_menu

router = Router()

router.message.middleware(RoleMiddleware(required_roles=['admin', 'manager']))
router.callback_query.middleware(RoleMiddleware(required_roles=['admin', 'manager']))


# ✅ НОВЫЙ ХЭНДЛЕР: Нажатие кнопки "Изменить дату доставки"
@router.callback_query(OrderEditingStates.my_order_menu, F.data.startswith("change_date_start_"))
async def edit_delivery_date_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Начинает процесс изменения даты доставки.
    Выводит календарь для выбора новой даты (только будущие даты, до +7 дней).
    """
    await bot(callback.answer()) # Отвечаем на CallbackQuery немедленно
    order_id = int(callback.data.split("_")[-1])
    # order_id уже есть в state.data как editing_order_id, но можно перепроверить

    await bot(callback.message.edit_text("Пожалуйста, выберите новую дату доставки:", parse_mode="MarkdownV2"))

    today = datetime.date.today()
    buttons = []
    for i in range(0, 8): # От 0 (сегодня) до 7 дней вперед
        date_to_show = today + datetime.timedelta(days=i)
        button_text = date_to_show.strftime("%d.%m.%Y")
        callback_data = f"select_new_delivery_date_{date_to_show.isoformat()}"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])
    
    buttons.append([InlineKeyboardButton(text="❌ Отмена изменения даты", callback_data="cancel_delivery_date_edit")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await bot(callback.message.edit_reply_markup(reply_markup=keyboard))
    await state.set_state(OrderEditingStates.waiting_for_new_delivery_date)


# ✅ НОВЫЙ ХЭНДЛЕР: Выбор новой даты доставки
@router.callback_query(OrderEditingStates.waiting_for_new_delivery_date, F.data.startswith("select_new_delivery_date_"))
async def process_new_delivery_date_selection(callback: CallbackQuery, state: FSMContext, bot: Bot): # bot добавлен
    """
    Обрабатывает выбор новой даты доставки.
    Обновляет дату доставки заказа (delivery_date) в БД.
    """
    await bot(callback.answer()) # Отвечаем на CallbackQuery немедленно
    new_delivery_date_str = callback.data.split("_")[-1]
    try:
        new_delivery_date = datetime.date.fromisoformat(new_delivery_date_str)
    except ValueError:
        await bot(callback.answer("Ошибка: Некорректный формат даты. Пожалуйста, попробуйте еще раз.", show_alert=True))
        await edit_delivery_date_start(callback, state, bot)
        return

    data = await state.get_data()
    order_id = data.get('editing_order_id')

    if not order_id:
        await bot(callback.answer("Ошибка: Заказ для обновления даты не найден.", show_alert=True))
        await state.clear()
        await bot(callback.message.edit_text("Пожалуйста, начните /my_orders снова."))
        return

    async for session in get_db_session():
        try:
            order_stmt = select(Order).where(Order.order_id == order_id)
            order_result = await session.execute(order_stmt)
            order = order_result.scalar_one_or_none()

            if order:
                order.delivery_date = new_delivery_date
                await session.commit()
                # ✅ ИСПРАВЛЕНИЕ ЗДЕСЬ: УДАЛЯЕМ bold() И parse_mode="MarkdownV2"
                await bot(callback.message.edit_text(f"✅ Дата доставки для заказа №{order_id} успешно обновлена на: {new_delivery_date.strftime('%d.%m.%Y')}!")) # <--- УДАЛЕНО: parse_mode="MarkdownV2"
                await return_to_order_menu(callback, state, bot)
            else:
                await bot(callback.message.edit_text("Ошибка: Заказ не найден для обновления даты доставки.")) # <--- УДАЛЕНО: parse_mode="MarkdownV2"
                await session.rollback()
                await state.clear()
        except Exception as e:
            await session.rollback()
            # ✅ ИСПРАВЛЕНИЕ ЗДЕСЬ: УДАЛЯЕМ bold() И parse_mode="MarkdownV2"
            await bot(callback.message.edit_text(f"❌ Произошла ошибка при обновлении даты доставки: {str(e)}\n")) # <--- УДАЛЕНО: parse_mode="MarkdownV2"
            logging.error(f"Ошибка при обновлении даты доставки для заказа {order_id}: {e}", exc_info=True)
            await state.clear()
        # finally: # callback.answer() уже в начале
        #     await bot(callback.answer())


# ✅ НОВЫЙ ХЭНДЛЕР: Отмена изменения даты доставки
@router.callback_query(OrderEditingStates.waiting_for_new_delivery_date, F.data == "cancel_delivery_date_edit")
async def cancel_delivery_date_edit(callback: CallbackQuery, state: FSMContext, bot: Bot): # bot добавлен
    """
    Отменяет изменение даты доставки и возвращается в меню редактирования заказа.
    """
    await bot(callback.answer()) # Отвечаем на CallbackQuery немедленно
    data = await state.get_data()
    order_id = data.get('editing_order_id')
    
    await bot(callback.message.edit_text(f"Изменение даты доставки отменено. Возвращаюсь в меню редактирования заказа №{order_id}.")) # <--- УДАЛЕНО: parse_mode="MarkdownV2"
    
    await process_my_order_selection(callback, state, bot) # Повторно вызываем меню редактирования для этого заказа
    # finally: # callback.answer() уже в начале
    #     await bot(callback.answer())