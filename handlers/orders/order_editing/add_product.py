# handlers/orders/order_editing/add_product.py

import datetime
import logging
from decimal import Decimal

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from middlewares.role_middleware import RoleMiddleware
from db.setup import get_db_session
from db.models import Order, OrderLine, Product # Убедитесь, что все эти модели импортированы
from sqlalchemy.future import select
from sqlalchemy import insert # Добавляем insert
from utils.text_formatter import escape_markdown_v2, bold, italic
from states.order_states import OrderEditingStates, OrderCreationStates # Нужен OrderCreationStates для wait_for_product_quantity

# Импортируем функцию для возврата в меню редактирования из главного файла edit_order.py
# А также process_my_order_selection, если ее нужно вызывать для возврата
from handlers.orders.edit_order import process_my_order_selection, return_to_order_menu

router = Router()

router.message.middleware(RoleMiddleware(required_roles=['admin', 'manager']))
router.callback_query.middleware(RoleMiddleware(required_roles=['admin', 'manager']))

# ✅ НОВЫЙ ХЭНДЛЕР: Нажатие кнопки "Добавить товар в заказ"
@router.callback_query(OrderEditingStates.my_order_menu, F.data.startswith("add_product_start_")) # <--- ПРОВЕРЬТЕ ЭТИ ФИЛЬТРЫ
async def add_product_to_order_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Начинает процесс добавления нового товара в существующий заказ.
    """
    await bot(callback.answer())
    order_id = int(callback.data.split("_")[-1])
    await state.update_data(editing_order_id=order_id, adding_to_existing_order=True) # Устанавливаем флаг
    
    await send_product_options(callback, state, bot) # Вызываем функцию выбора товара
    logging.debug(f"add_product_to_order_start: Состояние установлено на {OrderCreationStates.waiting_for_product_selection}")

# Обязательно убедитесь, что функция send_product_options принимает 'bot'
async def send_product_options(update_obj: Message | CallbackQuery, state: FSMContext, bot: Bot):
    """
    Отправляет список товаров для добавления в заказ.
    """
    async for session in get_db_session():
        products_stmt = select(Product)
        products_result = await session.execute(products_stmt)
        products = products_result.scalars().all()

        if not products:
            if isinstance(update_obj, Message):
                await update_obj.answer("В системе пока нет зарегистрированных товаров. Пожалуйста, добавьте их сначала.")
            else:
                await update_obj.message.edit_text("В системе пока нет зарегистрированных товаров. Пожалуйста, добавьте их сначала.")
            await state.clear()
            return

        buttons = []
        for product in products:
            button_text = f"{product.name} ({product.price} грн)" # Без parse_mode, поэтому без экранирования внутри f-строки
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"select_product_order_{product.product_id}")])

        buttons.append([InlineKeyboardButton(text="↩️ Назад к выбору адреса", callback_data="back_to_address_selection")])
        buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order_creation")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        message_text = "Выберите товар для добавления в заказ:"
        if isinstance(update_obj, Message):
            await update_obj.answer(message_text, reply_markup=keyboard) # Убрали parse_mode
        else: # CallbackQuery
            await update_obj.message.edit_text(message_text, reply_markup=keyboard) # Убрали parse_mode

        await state.set_state(OrderCreationStates.waiting_for_product_selection)


@router.callback_query(OrderCreationStates.waiting_for_product_selection, F.data.startswith("select_product_order_"))
async def process_product_selection_order(callback: CallbackQuery, state: FSMContext, bot: Bot): # bot добавлен
    """
    Обрабатывает выбор товара.
    Запрашивает количество товара для заказа.
    """
    await bot(callback.answer()) # Отвечаем на CallbackQuery немедленно
    product_id = int(callback.data.split("_")[-1])
    async for session in get_db_session():
        product_stmt = select(Product).where(Product.product_id == product_id)
        product_result = await session.execute(product_stmt)
        product = product_result.scalar_one_or_none()

        if product:
            await state.update_data(current_order_product_id=product.product_id,
                                    current_order_product_name=product.name,
                                    current_order_product_price=product.price) # Сохраняем цену продажи
            await bot(callback.message.edit_text(f"Вы выбрали товар: {bold(escape_markdown_v2(product.name))}\n"
                                             "Пожалуйста, введите количество товара для заказа:",
                                             parse_mode="MarkdownV2"))
            await state.set_state(OrderCreationStates.waiting_for_product_quantity)
        else:
            await bot(callback.answer("Ошибка: Товар не найден. Пожалуйста, попробуйте еще раз.", show_alert=True))
            await send_product_options(callback, state, bot) # Возвращаемся к выбору товара


@router.message(OrderCreationStates.waiting_for_product_quantity, F.text.regexp(r'^\d+$'))
async def process_product_quantity_order(message: Message, state: FSMContext, bot: Bot): # bot: Bot ДОБАВЛЕН
    """
    Обрабатывает ввод нового количества товара.
    Обновляет БД и возвращается в меню редактирования заказа.
    """
    try:
        new_quantity = int(message.text)
        if new_quantity <= 0:
            await message.answer("Количество должно быть положительным целым числом. Пожалуйста, введите корректное количество.")
            return
    except ValueError:
        await message.answer("Пожалуйста, введите корректное целое числовое значение для количества.")
        return

    data = await state.get_data()
    order_line_id = data.get('editing_order_line_id') # Это поле будет только если мы из режима редактирования
    order_id = data.get('editing_order_id') # ID заказа, если мы из режима редактирования

    # Определяем, находимся ли мы в режиме "добавления товара к существующему заказу"
    adding_to_existing_order = data.get('adding_to_existing_order', False)

    current_product_id = data['current_order_product_id']
    current_product_name = data['current_order_product_name']
    unit_price = Decimal(str(data['current_order_product_price']))
    line_total = Decimal(str(new_quantity)) * unit_price

    # Загружаем текущий список order_items из состояния, если он есть
    order_items = data.get('order_items', [])

    order_items.append({
        'product_id': current_product_id,
        'product_name': current_product_name,
        'quantity': new_quantity,
        'unit_price': unit_price,
        'line_total': line_total
    })
    await state.update_data(order_items=order_items)

    delivery_date = data.get('delivery_date')
    if not delivery_date and not adding_to_existing_order: # Если дата еще не установлена и это не режим редактирования
        delivery_date = datetime.date.today() + datetime.timedelta(days=1)
        await state.update_data(delivery_date=delivery_date)
    
    current_total_sum = sum((item['line_total'] for item in order_items), start=Decimal('0'))

    if adding_to_existing_order:
        async for session in get_db_session():
            try:
                order_stmt = select(Order).where(Order.order_id == order_id)
                order_result = await session.execute(order_stmt)
                order = order_result.scalar_one_or_none()

                if not order:
                    await message.answer("Ошибка: Основной заказ не найден для добавления товара. Пожалуйста, начните /my_orders снова.")
                    await state.clear()
                    logging.error(f"process_product_quantity_order: Order {order_id} не найден при добавлении товара.")
                    return

                insert_stmt_order_line = insert(OrderLine).values(
                    order_id=order_id,
                    product_id=current_product_id,
                    quantity=new_quantity,
                    unit_price=unit_price,
                )
                await session.execute(insert_stmt_order_line)
                logging.info(f"Новая OrderLine для product_id {current_product_id} добавлена в заказ {order_id}.")

                order.total_amount += line_total
                logging.info(f"Общая сумма заказа {order_id} увеличена на {line_total}.")

                await session.commit()
                logging.info("Транзакция успешно закоммичена: новый товар добавлен в заказ и сумма обновлена.")

                await message.answer(
                    f"✅ Товар '{escape_markdown_v2(current_product_name)}' ({new_quantity} шт.) добавлен в заказ №{order_id}.\n"
                    f"Текущая сумма заказа: {escape_markdown_v2(str(round(order.total_amount, 2)))} грн."
                )
                
                await state.update_data(adding_to_existing_order=False)
                temp_callback = CallbackQuery(
                    id=f"temp_{datetime.datetime.now().timestamp()}",
                    from_user=message.from_user,
                    # ✅ ИСПРАВЛЕНИЕ: Используем message.chat.id вместо message.chat_instance
                    chat_instance=str(message.chat.id), # <--- ИСПРАВЛЕНО ЗДЕСЬ
                    message=message,
                    data=f"edit_order_select_{order_id}"
                )
                await process_my_order_selection(temp_callback, state, bot)
                logging.info("Возвращение в меню редактирования после добавления товара.")
                return # Завершаем выполнение хэндлера

            except Exception as e:
                await session.rollback()
                await message.answer(f"❌ Произошла ошибка при добавлении товара в заказ: {str(e)}\n")
                logging.error(f"process_product_quantity_order: Ошибка при добавлении товара в заказ {order_id}: {e}", exc_info=True)
                await state.clear()
                return

    summary_text = f"{bold('Текущая позиция добавлена в заказ:')}\n" \
                   f"  Товар: {bold(escape_markdown_v2(current_product_name))}\n" \
                   f"  Количество: {bold(str(new_quantity))} шт\\.\n" \
                   f"  Цена/ед: {bold(str(unit_price))} грн\n" \
                   f"  Сумма по позиции: {bold(str(round(line_total, 2)))} грн\n\n" \
                   f"{bold('Автоматическая дата доставки:')} {bold(delivery_date.strftime('%d.%m.%Y'))}\n\n" \
                   f"{bold('Всего позиций в заказе:')} {bold(str(len(order_items)))}\n" \
                   f"{bold('Общая сумма заказа:')} {bold(str(round(current_total_sum, 2)))} грн\n\n" \
                   "Что дальше?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить еще товар", callback_data="add_another_order_product")],
        [InlineKeyboardButton(text="✅ Завершить формирование заказа", callback_data="complete_order_creation")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order_creation")]
    ])

    await message.answer(summary_text, reply_markup=keyboard, parse_mode="MarkdownV2")
    await state.set_state(OrderCreationStates.confirming_order_item)


# ✅ НОВЫЙ ХЭНДЛЕР: Добавить еще товар (для решения Проблемы 1)
@router.callback_query(OrderCreationStates.confirming_order_item, F.data == "add_another_order_product")
async def add_another_order_product_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Обрабатывает нажатие кнопки "Добавить еще товар" и возвращает к выбору товара.
    """
    await bot(callback.answer())
    # Возвращаемся к выбору товара
    await send_product_options(callback, state, bot)

# ... (остальной код add_product_order.py) ...