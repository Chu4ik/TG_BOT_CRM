# services/order_editing_service.py

import datetime
import logging
from decimal import Decimal

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from db.setup import get_db_session
from db.models import Order, Client, Employee, Address, OrderLine, Product
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from utils.text_formatter import escape_markdown_v2, bold, italic
from states.order_states import OrderEditingStates


async def process_my_order_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Обрабатывает выбор заказа для редактирования.
    Выводит полную информацию о заказе и предлагает опции редактирования.
    """
    # await bot(callback.answer()) # <--- УДАЛИТЬ ЭТУ СТРОКУ! (Она вызвала ошибку)
    
    order_id = int(callback.data.split("_")[-1])
    await state.update_data(editing_order_id=order_id)

    async for session in get_db_session():
        try:
            order_stmt = select(Order).where(Order.order_id == order_id).options(
                selectinload(Order.client),
                selectinload(Order.employee),
                selectinload(Order.address),
                selectinload(Order.order_lines).selectinload(OrderLine.product)
            )
            order_result = await session.execute(order_stmt)
            order = order_result.scalar_one_or_none()

            if not order:
                await bot.send_message(callback.message.chat.id, bold("❌ Заказ не найден."))
                await state.clear()
                return

            client_name = order.client.name if order.client else 'Неизвестно'
            employee_name = order.employee.name if order.employee else 'Неизвестно'
            address_text = order.address.address_text if order.address else 'Не указан'


            summary_parts = [
                f"Информация о заказе №{order.order_id} ({order.status})\n\n",

                f"Клиент: {client_name}\n",
                f"Сотрудник: {employee_name}\n",
                f"Адрес: {address_text}\n",
                f"Дата создания: {order.order_date.strftime('%d.%m.%Y %H:%M')}\n",
                f"Дата доставки: {order.delivery_date.strftime('%d.%m.%Y') if order.delivery_date else 'Не указана'}\n",
                f"Сумma: {round(order.total_amount, 2)} грн\n\n",
            ]

            if order.invoice_number:
                summary_parts.append(f"Номер накладной: {order.invoice_number}\n")

            summary_parts.append("\n--- Товары в заказе ---\n")

            if order.order_lines:
                sorted_order_lines = sorted(order.order_lines, key=lambda x: x.order_line_id)

                for idx, line in enumerate(sorted_order_lines):
                    product_name = line.product.name if line.product else "Неизвестный товар"
                    quantity = str(line.quantity)
                    unit_price = str(round(line.unit_price, 2))
                    line_total = str(round(line.line_total, 2))

                    summary_parts.append(
                        f"{idx+1}. {product_name}\n"
                        f"   Кол-во: {quantity} шт. | Цена: {unit_price} грн | Сумма: {line_total} грн\n"
                    )
            else:
                summary_parts.append("В этом заказе нет товаров.\n")

            summary_parts.append("\n--- Итого ---\n")
            summary_parts.append(f"Общая сумма заказа: {round(order.total_amount, 2)} грн\n")
            summary_parts.append(f"Оплачено: {round(order.amount_paid, 2)} грн\n")
            remaining_amount = order.total_amount - order.amount_paid
            summary_parts.append(f"Остаток к оплате: {round(remaining_amount, 2)} грн\n")


            full_summary_text = "".join(summary_parts)

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Изменить количество товара", callback_data=f"change_quantity_start_{order_id}")],
                [InlineKeyboardButton(text="🗑️ Удалить товар из заказа", callback_data=f"delete_product_start_{order_id}")],
                [InlineKeyboardButton(text="➕ Добавить товар в заказ", callback_data=f"add_product_start_{order_id}")],
                [InlineKeyboardButton(text="📅 Изменить дату доставки", callback_data=f"change_date_start_{order_id}")],
                [InlineKeyboardButton(text="🗑️ Удалить заказ полностью", callback_data=f"delete_order_start_{order_id}")],
                [InlineKeyboardButton(text="✅ Готово (вернуться в меню)", callback_data="done_editing_order")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_order_editing")]
            ])

            await bot.send_message( # <--- Отправляем НОВОЕ сообщение
                chat_id=callback.message.chat.id,
                text=full_summary_text,
                reply_markup=keyboard
            )
            # Если нужно удалить старое сообщение, используйте delete_message
            if callback.message: # Проверяем, существует ли сообщение для удаления
                try:
                    await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
                except Exception as del_e:
                    logging.warning(f"Не удалось удалить старое сообщение: {del_e}")


            await state.set_state(OrderEditingStates.my_order_menu)

        except Exception as e:
            await session.rollback()
            await bot.send_message(callback.message.chat.id, f"❌ Произошла ошибка при загрузке заказа: {str(e)}\n")
            logging.error(f"Ошибка при загрузке заказа {order_id}: {e}", exc_info=True)
            await state.clear()
        # finally: # <--- УДАЛИТЬ: callback.answer() должен быть вызван вызывающим хэндлером
        #     await bot(callback.answer())


async def return_to_order_menu(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Возвращает пользователя в меню редактирования конкретного заказа
    после операций редактирования/удаления позиции/даты.
    """
    # await bot(callback.answer()) # <--- УДАЛИТЬ ЭТУ СТРОКУ! (Она вызвала ошибку)

    data = await state.get_data()
    order_id = data.get('editing_order_id')

    if not order_id:
        await bot.send_message(callback.message.chat.id, "Ошибка: Заказ для возврата в меню не найден. Пожалуйста, начните /my_orders снова.")
        await state.clear()
        await bot(callback.answer()) # Здесь answer нужен, если это последний шаг
        return

    # Вызываем process_my_order_selection, которая теперь ОТПРАВЛЯЕТ НОВОЕ сообщение
    temp_callback_data = f"edit_order_select_{order_id}"
    temp_callback = CallbackQuery(
        id=f"temp_{datetime.datetime.now().timestamp()}",
        from_user=callback.from_user,
        chat_instance=callback.chat_instance,
        message=callback.message,
        data=temp_callback_data
    )
    await process_my_order_selection(temp_callback, state, bot)
    # Здесь callback.answer() НЕ ВЫЗЫВАЕТСЯ, так как process_my_order_selection
    # теперь отправляет новое сообщение и implicit answer происходит с ним.
    # Если это CallbackQuery, и мы не edit_text, то answer() все еще нужен.
    # Давайте явно ответим на callback.answer() здесь, чтобы не было "висящих" запросов.
    await bot(callback.answer()) # <--- ИСПРАВЛЕНО, ответ на этот callback_query