import datetime
import logging
from decimal import Decimal

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from middlewares.role_middleware import RoleMiddleware
from db.setup import get_db_session
from db.models import Order, OrderLine, Product
from sqlalchemy.future import select
from sqlalchemy import update
from sqlalchemy.orm import selectinload
from utils.text_formatter import escape_markdown_v2, bold, italic
from states.order_states import OrderEditingStates

from services.order_editing_service import process_my_order_selection, return_to_order_menu

router = Router()

router.message.middleware(RoleMiddleware(required_roles=['admin', 'manager']))
router.callback_query.middleware(RoleMiddleware(required_roles=['admin', 'manager']))


@router.callback_query(OrderEditingStates.my_order_menu, F.data.startswith("change_quantity_start_"))
async def edit_item_quantity_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Начинает процесс изменения количества товара в заказе.
    Выводит список товаров в текущем заказе для выбора.
    """
    await bot(callback.answer())
    order_id = int(callback.data.split("_")[-1])
    # Сохраняем order_id в состоянии, если он еще не там
    current_data = await state.get_data()
    if 'editing_order_id' not in current_data or current_data['editing_order_id'] != order_id:
        await state.update_data(editing_order_id=order_id)
        logging.debug(f"edit_item_quantity_start: Состояние 'editing_order_id' установлено на {order_id}")


    async for session in get_db_session():
        try:
            order_lines_stmt = select(OrderLine).where(OrderLine.order_id == order_id).options(selectinload(OrderLine.product))
            order_lines_result = await session.execute(order_lines_stmt)
            order_lines = order_lines_result.scalars().all()

            if not order_lines:
                await bot(callback.answer("В этом заказе нет товаров для изменения количества.", show_alert=True))
                await process_my_order_selection(callback, state, bot)
                return

            buttons = []
            for line in order_lines:
                product_name = escape_markdown_v2(line.product.name if line.product else "Неизвестный товар")
                quantity = escape_markdown_v2(str(line.quantity))
                unit_price = escape_markdown_v2(str(round(line.unit_price, 2)))

                button_text = f"{product_name} ({quantity} шт. по {unit_price} грн)"
                buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"select_item_to_edit_qty_{line.order_line_id}")])

            buttons.append([InlineKeyboardButton(text="❌ Отмена изменения количества позиции", callback_data="cancel_item_quantity_edit")])

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await bot(callback.message.edit_text("Выберите товар, количество которого хотите изменить:", reply_markup=keyboard, parse_mode="MarkdownV2"))
            await state.set_state(OrderEditingStates.waiting_for_item_to_edit_quantity)
            logging.debug(f"edit_item_quantity_start: Состояние установлено на {OrderEditingStates.waiting_for_item_to_edit_quantity}")

        except Exception as e:
            await session.rollback()
            await bot(callback.message.edit_text(f"{bold('❌ Произошла ошибка при загрузке позиций для изменения количества:')}\n{escape_markdown_v2(str(e))}", parse_mode="MarkdownV2"))
            logging.error(f"Ошибка при загрузке позиций для изменения количества из заказа {order_id}: {e}", exc_info=True)
            await state.clear()


@router.callback_query(OrderEditingStates.waiting_for_item_to_edit_quantity, F.data.startswith("select_item_to_edit_qty_"))
async def process_item_to_edit_quantity(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Обрабатывает выбор позиции товара для изменения количества.
    Запрашивает новое количество.
    """
    await bot(callback.answer())
    
    current_state = await state.get_state()
    logging.debug(f"process_item_to_edit_quantity: Текущее состояние бота: {current_state}")

    order_line_id = int(callback.data.split("_")[-1])
    
    data = await state.get_data()
    order_id = data.get('editing_order_id')

    if not order_id:
        await bot(callback.message.edit_text("Ошибка: ID заказа не найден в состоянии. Пожалуйста, начните /my_orders снова."))
        await state.clear()
        logging.error("process_item_to_edit_quantity: order_id не найден в состоянии.")
        return

    await state.update_data(editing_order_line_id=order_line_id)
    logging.debug(f"process_item_to_edit_quantity: editing_order_line_id установлен на {order_line_id}")


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
                logging.warning(f"process_item_to_edit_quantity: OrderLine с ID {order_line_id} не найден.")
                return

            product_name = escape_markdown_v2(order_line.product.name if order_line.product else "Неизвестный товар")
            current_quantity = escape_markdown_v2(str(order_line.quantity))

            await bot(callback.message.edit_text(
                f"{bold(f'Вы выбрали товар:')}\n"
                f"Товар: {product_name}\n"
                f"Текущее количество: {current_quantity} шт\\. по {escape_markdown_v2(str(round(order_line.unit_price, 2)))} грн\\)\n"
                f"Введите новое количество:",
                parse_mode="MarkdownV2"
            ))
            await state.set_state(OrderEditingStates.waiting_for_new_quantity)
            logging.debug(f"process_item_to_edit_quantity: Состояние установлено на {OrderEditingStates.waiting_for_new_quantity}")
            
        except Exception as e:
            await session.rollback()
            await bot(callback.message.edit_text(f"{bold('❌ Произошла ошибка при подготовке к изменению количества:')}\n{escape_markdown_v2(str(e))}", parse_mode="MarkdownV2"))
            logging.error(f"Ошибка при подготовке к изменению количества позиции {order_line_id} из заказа {order_id}: {e}", exc_info=True)
            await state.clear()


@router.message(OrderEditingStates.waiting_for_new_quantity, F.text.regexp(r'^\d+$'))
async def process_new_quantity(message: Message, state: FSMContext, bot: Bot):
    """
    Обрабатывает ввод нового количества товара.
    Обновляет БД и возвращается в меню редактирования заказа.
    """
    try:
        new_quantity = int(message.text) # Используем int, т.к. quantity в БД integer (согласно вашему \d)
        if new_quantity <= 0:
            await message.answer("Количество должно быть положительным целым числом. Пожалуйста, введите корректное количество.")
            return
    except ValueError:
        await message.answer("Пожалуйста, введите корректное целое числовое значение для количества.")
        return

    data = await state.get_data()
    order_line_id = data.get('editing_order_line_id')
    order_id_from_state = data.get('editing_order_id')

    if not order_line_id or not order_id_from_state:
        await message.answer("Ошибка: Не удалось определить позицию или заказ. Пожалуйста, начните /my_orders снова.")
        await state.clear()
        logging.error("process_new_quantity: order_line_id или order_id не найдены в состоянии.")
        return

    async for session in get_db_session():
        try:
            # Загружаем позицию заказа, включая связанный продукт для получения имени
            order_line_stmt = select(OrderLine).where(OrderLine.order_line_id == order_line_id).options(selectinload(OrderLine.product))
            order_line_result = await session.execute(order_line_stmt)
            order_line = order_line_result.scalar_one_or_none()

            if not order_line:
                await message.answer("Ошибка: Позиция заказа не найдена для обновления.")
                temp_callback = CallbackQuery(
                    id=f"temp_no_line_{datetime.datetime.now().timestamp()}",
                    from_user=message.from_user,
                    chat_instance=message.chat_instance,
                    message=message,
                    data=f"edit_order_select_{order_id_from_state}"
                )
                await process_my_order_selection(temp_callback, state, bot) # Передаем bot
                logging.warning(f"process_new_quantity: OrderLine с ID {order_line_id} не найден.")
                return

            old_quantity = order_line.quantity
            old_line_total = Decimal(str(old_quantity)) * order_line.unit_price

            order_line.quantity = new_quantity # Обновляем количество в объекте ORM
            
            # Расчет new_line_total для обновления total_amount
            new_line_total = Decimal(str(new_quantity)) * order_line.unit_price # Этот расчет нужен для total_amount

            # Загружаем объект Order, чтобы обновить его total_amount
            order_stmt = select(Order).where(Order.order_id == order_id_from_state)
            order_result = await session.execute(order_stmt)
            order = order_result.scalar_one_or_none()

            if order: # Проверяем, что 'order' найден, прежде чем его использовать
                order.total_amount = order.total_amount - old_line_total + new_line_total
                
                await session.commit() # ЕДИНСТВЕННЫЙ COMMIT В КОНЦЕ УСПЕШНОЙ ЛОГИКИ
                logging.info("Транзакция успешно закоммичена: количество позиции и общая сумма заказа обновлены.")

                # ✅ ИСПРАВЛЕНИЕ ЗДЕСЬ: УДАЛЯЕМ parse_mode="MarkdownV2" И bold/escape_markdown_v2
                # Сообщение об успехе как ПЛЕЙН ТЕКСТ.
                success_message_parts = [
                    '✅ Количество успешно обновлено:', "\n",
                    "Товар: ", (order_line.product.name), "\n", # Без escape_markdown_v2
                    "Было: ", str(old_quantity), " шт.\n", # Без escape_markdown_v2, обычная точка
                    "Стало: ", str(new_quantity), " шт.\n", # Без escape_markdown_v2, обычная точка
                    "Новая сумма заказа: ", str(round(order.total_amount, 2)), " грн" # Без escape_markdown_v2, обычная точка
                ]
                final_success_message = "".join(success_message_parts)


                await message.answer(
                    final_success_message # Передаем собранную и теперь полностью НЕформатированную строку
                    # parse_mode="MarkdownV2" # <--- ЭТУ СТРОКУ НУЖНО УДАЛИТЬ!
                )
                
                temp_callback = CallbackQuery(
                    id=f"temp_{datetime.datetime.now().timestamp()}",
                    from_user=message.from_user,
                    chat_instance=getattr(message, 'chat_instance', str(message.chat.id)),
                    message=message,
                    data=f"edit_order_select_{order_id_from_state}"
                )
                await process_my_order_selection(temp_callback, state, bot) # Передаем bot
                logging.info("Возвращение в меню редактирования после успешного обновления количества.")
            else:
                await message.answer("Ошибка: Заказ не найден для обновления общей суммы. Изменения отменены.")
                await session.rollback()
                logging.warning(f"process_new_quantity: Order с ID {order_id_from_state} не найден для обновления суммы.")
                await state.clear()


        except Exception as e:
            await session.rollback()
            # ✅ ИСПРАВЛЕНИЕ ЗДЕСЬ: Убираем bold/escape_markdown_v2 из сообщения об ошибке
            # Сообщение об ошибке как ПЛЕЙН ТЕКСТ.
            await message.answer(f"❌ Произошла ошибка при обновлении количества: {str(e)}\n")
            print(f"Ошибка при обновлении количества: {e}")
            logging.error(f"process_new_quantity: Непредвиденная ошибка: {e}", exc_info=True)
            await state.clear()


@router.message(OrderEditingStates.waiting_for_new_quantity)
async def process_new_quantity_invalid(message: Message, state: FSMContext, bot: Bot):
    """
    Обрабатывает некорректный ввод количества.
    """
    await message.answer(f"{bold('Некорректный ввод\\!')} Пожалуйста, введите целое число для количества\\.", parse_mode="MarkdownV2")


@router.callback_query(OrderEditingStates.waiting_for_item_to_edit_quantity, F.data == "cancel_item_quantity_edit")
async def cancel_item_quantity_edit(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Отменяет процесс изменения количества и возвращается в меню редактирования заказа.
    """
    await bot(callback.answer())
    data = await state.get_data()
    order_id = data.get('editing_order_id')
    
    await bot(callback.message.edit_text(f"{bold('Изменение количества отменено.')}", parse_mode="MarkdownV2"))
    await process_my_order_selection(callback, state, bot)