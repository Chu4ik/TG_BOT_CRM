# handlers/orders/order_editing/delete_order.py

import datetime
import logging

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from middlewares.role_middleware import RoleMiddleware
from db.setup import get_db_session
from db.models import Order, OrderLine
from sqlalchemy import delete
from sqlalchemy.future import select
from utils.text_formatter import bold, escape_markdown_v2 # bold и escape_markdown_v2 импортированы
from states.order_states import OrderEditingStates
from services.order_editing_service import process_my_order_selection

router = Router()
router.message.middleware(RoleMiddleware(required_roles=['admin', 'manager']))
router.callback_query.middleware(RoleMiddleware(required_roles=['admin', 'manager']))


@router.callback_query(OrderEditingStates.my_order_menu, F.data.startswith("delete_order_start_"))
async def delete_order_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Начинает процесс удаления всего заказа.
    Запрашивает подтверждение.
    """
    await bot(callback.answer())
    order_id = int(callback.data.split("_")[-1])
    await state.update_data(deleting_order_id=order_id)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить весь заказ", callback_data="confirm_delete_order_yes")],
        [InlineKeyboardButton(text="❌ Нет, отмена", callback_data="confirm_delete_order_no")]
    ])

    # ✅ ИСПРАВЛЕНИЕ ЗДЕСЬ: УДАЛЯЕМ bold() И parse_mode="MarkdownV2"
    await bot(callback.message.edit_text(
        f"Вы уверены, что хотите полностью удалить заказ №{order_id}? Это действие необратимо!", # Простой текст
        reply_markup=keyboard,
        # parse_mode="MarkdownV2" # <--- УДАЛИТЕ ЭТУ СТРОКУ
    ))
    await state.set_state(OrderEditingStates.waiting_for_order_delete_confirmation)


@router.callback_query(OrderEditingStates.waiting_for_order_delete_confirmation, F.data == "confirm_delete_order_yes")
async def confirm_delete_order_yes(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Подтверждает удаление всего заказа.
    """
    await bot(callback.answer())
    data = await state.get_data()
    order_id = data.get('deleting_order_id')

    if not order_id:
        await bot(callback.message.edit_text("Ошибка: ID заказа для удаления не найден. Пожалуйста, начните /my_orders снова."))
        await state.clear()
        logging.error("confirm_delete_order_yes: order_id не найден в состоянии.")
        return

    async for session in get_db_session():
        try:
            await session.execute(delete(Order).where(Order.order_id == order_id))
            
            await session.commit()
            logging.info(f"Транзакция успешно закоммичена: заказ {order_id} полностью удален.")

            # ✅ ИСПРАВЛЕНИЕ ЗДЕСЬ: УДАЛЯЕМ bold() И parse_mode="MarkdownV2"
            await bot(callback.message.edit_text(f"✅ Заказ №{order_id} успешно удален.")) # Простой текст
            await state.clear()
            logging.info("confirm_delete_order_yes: Состояние очищено после удаления заказа.")

        except Exception as e:
            await session.rollback()
            # ✅ ИСПРАВЛЕНИЕ ЗДЕСЬ: УДАЛЯЕМ bold() И parse_mode="MarkdownV2"
            await bot(callback.message.edit_text(f"❌ Произошла ошибка при удалении заказа: {str(e)}\n")) # Простой текст
            logging.error(f"Ошибка при удалении заказа {order_id}: {e}", exc_info=True)
            await state.clear()


@router.callback_query(OrderEditingStates.waiting_for_order_delete_confirmation, F.data == "confirm_delete_order_no")
async def confirm_delete_order_no(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Отменяет удаление всего заказа.
    """
    await bot(callback.answer())
    data = await state.get_data()
    order_id = data.get('deleting_order_id')
    
    # ✅ ИСПРАВЛЕНИЕ ЗДЕСЬ: УДАЛЯЕМ bold() И parse_mode="MarkdownV2"
    await bot(callback.message.edit_text(f"Удаление заказа №{order_id} отменено. Возвращаюсь в меню редактирования.")) # Простой текст
    
    # Чтобы вернуть в меню, вызываем service-функцию
    temp_callback_data = f"edit_order_select_{order_id}"
    temp_callback = CallbackQuery(
        id=f"temp_cancel_delete_order_{datetime.datetime.now().timestamp()}",
        from_user=callback.from_user,
        chat_instance=callback.chat_instance,
        message=callback.message,
        data=temp_callback_data
    )
    await process_my_order_selection(temp_callback, state, bot)