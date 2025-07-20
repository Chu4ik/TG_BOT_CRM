# handlers/orders/order_editing/delete_product.py

import datetime
import logging
from decimal import Decimal

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from middlewares.role_middleware import RoleMiddleware
from db.setup import get_db_session
from db.models import Order, OrderLine, Product # Убедитесь, что все эти модели импортированы
from sqlalchemy.future import select
from sqlalchemy import delete
from sqlalchemy.orm import selectinload
from utils.text_formatter import escape_markdown_v2, bold, italic
from states.order_states import OrderEditingStates # Убедитесь, что импортирован

# Импортируем функцию для возврата в меню редактирования из общего сервисного файла
from services.order_editing_service import process_my_order_selection, return_to_order_menu

router = Router()

router.message.middleware(RoleMiddleware(required_roles=['admin', 'manager']))
router.callback_query.middleware(RoleMiddleware(required_roles=['admin', 'manager']))


# ✅ НОВЫЙ ХЭНДЛЕР: Нажатие кнопки "Удалить товар из заказа"
@router.callback_query(OrderEditingStates.my_order_menu, F.data.startswith("delete_product_start_"))
async def delete_item_from_order_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Начинает процесс удаления товара из заказа.
    Выводит список товаров в текущем заказе для выбора.
    """
    await bot(callback.answer()) # Отвечаем на CallbackQuery немедленно
    order_id = int(callback.data.split("_")[-1])
    
    data = await state.get_data()
    if 'editing_order_id' not in data or data['editing_order_id'] != order_id:
        await state.update_data(editing_order_id=order_id)
        logging.debug(f"delete_item_from_order_start: Состояние 'editing_order_id' установлено на {order_id}")

    async for session in get_db_session():
        try:
            order_lines_stmt = select(OrderLine).where(OrderLine.order_id == order_id).options(selectinload(OrderLine.product))
            order_lines_result = await session.execute(order_lines_stmt)
            order_lines = order_lines_result.scalars().all()

            if not order_lines:
                await bot(callback.answer("В этом заказе нет товаров для удаления.", show_alert=True))
                # Возвращаемся в главное меню редактирования, если нет позиций
                temp_callback = CallbackQuery(
                    id=f"temp_no_items_del_prod_{datetime.datetime.now().timestamp()}", # Уникальный ID
                    from_user=callback.from_user,
                    chat_instance=callback.chat_instance,
                    message=callback.message,
                    data=f"edit_order_select_{order_id}"
                )
                await process_my_order_selection(temp_callback, state, bot)
                return

            buttons = []
            for line in order_lines:
                product_name = escape_markdown_v2(line.product.name if line.product else "Неизвестный товар")
                quantity = escape_markdown_v2(str(line.quantity))
                unit_price = escape_markdown_v2(str(round(line.unit_price, 2)))

                # ✅ Важно: экранируем весь текст, если используем MarkdownV2
                button_text = f"{product_name} ({quantity} шт. по {unit_price} грн)"
                buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"select_item_to_delete_{line.order_line_id}")])

            buttons.append([InlineKeyboardButton(text="❌ Отмена удаления позиции", callback_data="cancel_delete_item")])

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await bot(callback.message.edit_text("Выберите товар, который хотите удалить:", reply_markup=keyboard, parse_mode="MarkdownV2"))
            await state.set_state(OrderEditingStates.waiting_for_item_to_delete)
            logging.debug(f"delete_item_from_order_start: Состояние установлено на {OrderEditingStates.waiting_for_item_to_delete}")

        except Exception as e:
            await session.rollback()
            # ✅ Важно: экранируем текст ошибки, если используем MarkdownV2
            await bot(callback.message.edit_text(f"{bold('❌ Произошла ошибка при загрузке позиций для удаления:')}\n{escape_markdown_v2(str(e))}", parse_mode="MarkdownV2"))
            logging.error(f"Ошибка при загрузке позиций для удаления из заказа {order_id}: {e}", exc_info=True)
            await state.clear()


@router.callback_query(OrderEditingStates.waiting_for_item_to_delete, F.data.startswith("select_item_to_delete_"))
async def process_item_to_delete(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await bot(callback.answer())
    order_line_id = int(callback.data.split("_")[-1])
    
    data = await state.get_data()
    order_id = data.get('editing_order_id')

    if not order_id:
        await bot(callback.message.edit_text("Ошибка: ID заказа не найден в состоянии. Пожалуйста, начните /my_orders снова."))
        await state.clear()
        logging.error("process_item_to_delete: order_id не найден в состоянии.")
        return

    await state.update_data(deleting_order_line_id=order_line_id) # Сохраняем order_line_id для следующего шага

    async for session in get_db_session():
        try:
            order_line_stmt = select(OrderLine).where(OrderLine.order_line_id == order_line_id).options(selectinload(OrderLine.product))
            order_line_result = await session.execute(order_line_stmt)
            order_line = order_line_result.scalar_one_or_none()

            if not order_line:
                await bot(callback.answer("Ошибка: Позиция заказа не найдена.", show_alert=True))
                temp_callback = CallbackQuery(
                    id=f"temp_no_line_{datetime.datetime.now().timestamp()}",
                    from_user=callback.from_user,
                    chat_instance=callback.chat_instance,
                    message=callback.message,
                    data=f"edit_order_select_{order_id}"
                )
                await process_my_order_selection(temp_callback, state, bot)
                logging.warning(f"process_item_to_delete: OrderLine с ID {order_line_id} не найден.")
                return

            # ✅ ИСПРАВЛЕНИЕ: Получаем quantity и line_total из order_line здесь
            product_name = escape_markdown_v2(order_line.product.name if order_line.product else "Неизвестный товар")
            quantity = escape_markdown_v2(str(order_line.quantity)) # Получаем quantity из order_line
            line_total = escape_markdown_v2(str(round(order_line.line_total, 2))) # Получаем line_total из order_line

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да, удалить", callback_data="confirm_delete_line_yes")],
                [InlineKeyboardButton(text="❌ Нет, отмена", callback_data="confirm_delete_line_no")]
            ])

            await bot(callback.message.edit_text(
                f"{bold('Вы уверены, что хотите удалить эту позицию?')}\n"
                f"Товар: {product_name}\n"
                f"Количество: {quantity} шт\\. на сумму {line_total} грн\\.",
                reply_markup=keyboard,
                parse_mode="MarkdownV2"
            ))
            await state.set_state(OrderEditingStates.waiting_for_line_delete_confirmation)
            logging.debug(f"process_item_to_delete: Состояние установлено на {OrderEditingStates.waiting_for_line_delete_confirmation}")

        except Exception as e:
            await session.rollback()
            await bot(callback.message.edit_text(f"{bold('❌ Произошла ошибка при подготовке к удалению:')}\n{escape_markdown_v2(str(e))}", parse_mode="MarkdownV2"))
            logging.error(f"Ошибка при подготовке к удалению позиции {order_line_id} из заказа {order_id}: {e}", exc_info=True)
            await state.clear()


# ✅ НОВЫЙ ХЭНДЛЕР: Окончательное подтверждение удаления позиции
@router.callback_query(OrderEditingStates.waiting_for_line_delete_confirmation, F.data == "confirm_delete_line_yes") # ✅ ИСПРАВЛЕНО
async def confirm_delete_line_yes(callback: CallbackQuery, state: FSMContext, bot: Bot): # bot добавлен
    """
    Выполняет удаление позиции товара из заказа в БД, корректирует общую сумму.
    Логика обновления InventoryMovement и Stock ПЕРЕНЕСЕНА в админский функционал.
    """
    await bot(callback.answer()) # Отвечаем на CallbackQuery немедленно
    data = await state.get_data()
    order_line_id = data.get('deleting_order_line_id')
    order_id_from_state = data.get('editing_order_id')

    if not order_line_id or not order_id_from_state:
        await bot(callback.message.edit_text("Ошибка: Не удалось определить позицию или заказ для удаления. Пожалуйста, начните /my_orders снова."))
        await state.clear()
        logging.error("confirm_delete_line_yes: order_line_id или order_id не найдены в состоянии.")
        return

    async for session in get_db_session():
        try:
            order_line_stmt = select(OrderLine).where(OrderLine.order_line_id == order_line_id)
            order_line_result = await session.execute(order_line_stmt)
            order_line_to_delete = order_line_result.scalar_one_or_none()

            if not order_line_to_delete:
                await bot(callback.answer("Ошибка: Позиция заказа не найдена для удаления.", show_alert=True))
                temp_callback = CallbackQuery(
                    id=f"temp_no_line_del_prod_{datetime.datetime.now().timestamp()}", # Уникальный ID
                    from_user=callback.from_user,
                    chat_instance=callback.chat_instance,
                    message=callback.message,
                    data=f"edit_order_select_{order_id_from_state}"
                )
                await process_my_order_selection(temp_callback, state, bot)
                logging.warning(f"confirm_delete_line_yes: OrderLine с ID {order_line_id} не найден.")
                return

            deleted_line_total = order_line_to_delete.line_total

            await session.execute(delete(OrderLine).where(OrderLine.order_line_id == order_line_id))
            logging.info(f"OrderLine {order_line_id} удален из заказа {order_id_from_state}.")

            order_stmt = select(Order).where(Order.order_id == order_id_from_state)
            order_result = await session.execute(order_stmt)
            order = order_result.scalar_one_or_none()

            if order:
                order.total_amount = order.total_amount - deleted_line_total
                
                await session.commit()
                logging.info("Транзакция успешно закоммичена: позиция удалена и общая сумма заказа обновлена.")

                await bot(callback.message.edit_text(f"{bold('✅ Позиция успешно удалена.')}\n"
                                                    f"Новая сумма заказа: {escape_markdown_v2(str(round(order.total_amount, 2)))} грн",
                                                    parse_mode="MarkdownV2"))
                
                temp_callback = CallbackQuery(
                    id=f"temp_success_del_prod_{datetime.datetime.now().timestamp()}", # Уникальный ID
                    from_user=callback.from_user,
                    chat_instance=callback.chat_instance,
                    message=callback.message,
                    data=f"edit_order_select_{order_id_from_state}"
                )
                await process_my_order_selection(temp_callback, state, bot)
                logging.info("Возвращение в меню редактирования после успешного удаления позиции.")
            else:
                await bot(callback.answer("Ошибка: Заказ не найден для обновления общей суммы. Изменения отменены.", show_alert=True))
                await session.rollback()
                logging.warning(f"confirm_delete_line_yes: Order с ID {order_id_from_state} не найден для обновления суммы.")
                await state.clear()

        except Exception as e:
            await session.rollback()
            await bot(callback.message.edit_text(f"{bold('❌ Произошла ошибка при удалении позиции:')}\n{escape_markdown_v2(str(e))}", parse_mode="MarkdownV2"))
            logging.error(f"Ошибка при удалении позиции {order_line_id} из заказа {order_id_from_state}: {e}", exc_info=True)
            await state.clear()


@router.callback_query(OrderEditingStates.waiting_for_line_delete_confirmation, F.data == "confirm_delete_line_no") # ✅ ИСПРАВЛЕНО
async def confirm_delete_line_no(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Отменяет удаление позиции заказа.
    """
    await bot(callback.answer())
    data = await state.get_data()
    order_id = data.get('editing_order_id')
    
    await bot(callback.message.edit_text(f"{bold('Удаление позиции отменено.')}", parse_mode="MarkdownV2"))
    
    temp_callback = CallbackQuery(
        id=f"temp_cancel_del_prod_{datetime.datetime.now().timestamp()}", # Уникальный ID
        from_user=callback.from_user,
        chat_instance=callback.chat_instance,
        message=callback.message,
        data=f"edit_order_select_{order_id}"
    )
    await process_my_order_selection(temp_callback, state, bot)