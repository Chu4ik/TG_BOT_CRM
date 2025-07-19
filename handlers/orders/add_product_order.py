# handlers/orders/add_product_order.py

import datetime

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from middlewares.role_middleware import RoleMiddleware
from states.order_states import OrderCreationStates
from db.setup import get_db_session
from db.models import Product,Order, OrderLine, Employee
from sqlalchemy.future import select
from sqlalchemy import exc as sa_exc, insert
from utils.text_formatter import escape_markdown_v2, bold, italic
import logging

router = Router()

router.message.middleware(RoleMiddleware(required_roles=['admin', 'manager']))
router.callback_query.middleware(RoleMiddleware(required_roles=['admin', 'manager']))

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
            button_text = escape_markdown_v2(f"{product.name} ({product.price} грн)")
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"select_product_order_{product.product_id}")])

        buttons.append([InlineKeyboardButton(text="↩️ Назад к выбору адреса", callback_data="back_to_address_selection")])
        buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order_creation")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        message_text = "Выберите товар для добавления в заказ:"
        if isinstance(update_obj, Message):
            await update_obj.answer(message_text, reply_markup=keyboard, parse_mode="MarkdownV2")
        else: # CallbackQuery
            await update_obj.message.edit_text(message_text, reply_markup=keyboard, parse_mode="MarkdownV2")

        await state.set_state(OrderCreationStates.waiting_for_product_selection)

@router.callback_query(OrderCreationStates.waiting_for_product_selection, F.data.startswith("select_product_order_"))
async def process_product_selection_order(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор товара.
    Запрашивает количество товара для заказа.
    """
    product_id = int(callback.data.split("_")[-1])
    async for session in get_db_session():
        product_stmt = select(Product).where(Product.product_id == product_id)
        product_result = await session.execute(product_stmt)
        product = product_result.scalar_one_or_none()

        if product:
            await state.update_data(current_order_product_id=product.product_id,
                                    current_order_product_name=product.name,
                                    current_order_product_price=product.price) # Сохраняем цену продажи
            await callback.message.edit_text(f"Вы выбрали товар: {bold(escape_markdown_v2(product.name))}\n"
                                             "Пожалуйста, введите количество товара для заказа:",
                                             parse_mode="MarkdownV2")
            await state.set_state(OrderCreationStates.waiting_for_product_quantity)
        else:
            await callback.answer("Ошибка: Товар не найден. Пожалуйста, попробуйте еще раз.", show_alert=True)
            await send_product_options(callback, state, callback.bot) # Возвращаемся к выбору товара, передавая bot
    await callback.answer()

@router.message(OrderCreationStates.waiting_for_product_quantity, F.text)
async def process_product_quantity_order(message: Message, state: FSMContext):
    """
    Обрабатывает ввод количества товара для заказа.
    Добавляет позицию в заказ, автоматически устанавливает дату доставки
    и предлагает добавить еще или перейти к подтверждению заказа.
    """
    try:
        quantity = float(message.text.strip().replace(',', '.'))
        if quantity <= 0:
            await message.answer("Количество должно быть положительным числом. Пожалуйста, введите корректное количество.")
            return
    except ValueError:
        await message.answer("Пожалуйста, введите корректное числовое значение для количества.")
        return

    data = await state.get_data()
    product_id = data['current_order_product_id']
    product_name = data['current_order_product_name']
    unit_price = data['current_order_product_price'] # Используем цену продажи из Product
    line_total = quantity * unit_price

    order_items = data.get('order_items', [])
    order_items.append({
        'product_id': product_id,
        'product_name': product_name,
        'quantity': quantity,
        'unit_price': unit_price,
        'line_total': line_total
    })
    
    # ✅ НОВАЯ ЛОГИКА: Автоматическая установка даты доставки на завтра
    delivery_date = datetime.date.today() + datetime.timedelta(days=1)
    await state.update_data(order_items=order_items, delivery_date=delivery_date)


    summary_text = f"{bold('Текущая позиция добавлена в заказ:')}\n" \
               f"  Товар: {bold(escape_markdown_v2(product_name))}\n" \
               f"  Количество: {bold(str(quantity))} шт\\.\n" \
               f"  Цена/ед: {bold(str(unit_price))} грн\n" \
               f"  Сумма по позиции: {bold(str(round(line_total, 2)))} грн\n\n" \
               f"{bold('Автоматическая дата доставки:')} {bold(delivery_date.strftime('%d.%m.%Y'))}\n\n" \
               f"{bold('Всего позиций в заказе:')} {bold(str(len(order_items)))}\n" \
               f"{bold('Общая сумма заказа:')} {bold(str(round(sum(item['line_total'] for item in order_items), 2)))} грн\n\n" \
               "Что дальше?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить еще товар", callback_data="add_another_order_product")],
        [InlineKeyboardButton(text="✅ Завершить формирование заказа", callback_data="complete_order_creation")], # Изменено callback_data
        # Кнопка для выбора даты удалена, т.к. она теперь автоматическая
        # [InlineKeyboardButton(text="✏️ Редактировать заказ", callback_data="edit_order_items")] # Пока не реализуем
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order_creation")]
    ])

    await message.answer(summary_text, reply_markup=keyboard, parse_mode="MarkdownV2")
    await state.set_state(OrderCreationStates.confirming_order_item)

@router.callback_query(OrderCreationStates.confirming_order_item, F.data == "add_another_order_product")
async def add_another_order_product(callback: CallbackQuery, state: FSMContext):
    """
    Пользователь решил добавить еще один товар в текущий заказ.
    Возвращаемся к выбору товара.
    """
    await send_product_options(callback, state, callback.bot) # Используем общую функцию, передаем bot
    await callback.answer()

# ✅ НОВЫЙ ХЭНДЛЕР: Завершение формирования заказа
@router.callback_query(OrderCreationStates.confirming_order_item, F.data == "complete_order_creation")
async def complete_order_creation(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Завершает формирование заказа, выводит финальную сводку
    и предлагает сохранить или отменить.
    """
    data = await state.get_data()
    client_name = data.get('client_name')
    address_text = data.get('address_text')
    delivery_date = data.get('delivery_date')
    order_items = data.get('order_items', [])

    if not order_items:
        await callback.message.edit_text("Заказ пуст. Пожалуйста, добавьте хотя бы одну позицию.")
        await state.clear()
        await callback.answer()
        return

    total_order_amount = sum(item['line_total'] for item in order_items)

    # Формирование final_order_summary
    final_order_summary = f"{bold('Финальная сводка заказа:')}\n\n" \
                          f"Клиент: {bold(escape_markdown_v2(client_name))}\n" \
                          f"Адрес доставки: {bold(escape_markdown_v2(address_text))}\n" \
                          f"Дата доставки: {bold(delivery_date.strftime('%d.%m.%Y'))}\n\n" \
                          f"{bold('Позиции заказа:')}\n"

    for i, item in enumerate(order_items):
        final_order_summary += (
            f"{i+1}\\. "
            f"{escape_markdown_v2(item['product_name'])}: "
            f"{escape_markdown_v2(str(item['quantity']))} шт\\. x "
            f"{escape_markdown_v2(str(item['unit_price']))} грн \\= " # <--- Убрана точка после грн
            f"{escape_markdown_v2(str(round(item['line_total'], 2)))} грн\n" # <--- Убрана точка после грн
        )

    final_order_summary += f"\n{bold('Общая сумма заказа:')} {bold(escape_markdown_v2(str(round(total_order_amount, 2))))} грн"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить и сохранить заказ", callback_data="confirm_and_save_order")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order_creation")]
    ])

    await callback.message.edit_text(final_order_summary, reply_markup=keyboard, parse_mode="MarkdownV2")
    await state.set_state(OrderCreationStates.confirming_final_order)
    await callback.answer()

@router.callback_query(OrderCreationStates.confirming_final_order, F.data == "confirm_and_save_order")
async def confirm_and_save_order(callback: CallbackQuery, state: FSMContext, bot: Bot, db_user: Employee):
    """
    Сохраняет заказ и его позиции в базу данных.
    """
    logging.info("Начинаем сохранение заказа в БД.")
    data = await state.get_data()
    client_id = data.get('client_id')
    address_id = data.get('address_id')
    delivery_date = data.get('delivery_date')
    order_items = data.get('order_items', [])
    employee_id = db_user.employee_id # ID сотрудника из БД
    client_name = data.get('client_name', 'Неизвестный клиент') # Получаем имя клиента

    if not order_items:
        await callback.message.edit_text("Заказ пуст. Нет позиций для сохранения.")
        await state.clear()
        await callback.answer()
        logging.info("Сохранение отменено: заказ пуст.")
        return

    total_order_amount = sum(item['line_total'] for item in order_items)
    logging.info(f"Получены данные заказа: Клиент ID={client_id}, Адрес ID={address_id}, Дата доставки={delivery_date}, Всего позиций={len(order_items)}, Общая сумма={total_order_amount}")

    async for session in get_db_session(): # НАЧАЛО КОНТЕКСТА СЕССИИ
        try:
            logging.info("Сессия БД получена. Подготовка INSERT для Order.")
            # 1. Создаем запись в таблице orders, используя insert() для прямого получения ID
            insert_stmt_order = insert(Order).values(
                invoice_number=None, # Присваивается позже
                order_date=datetime.datetime.now(),
                delivery_date=delivery_date,
                employee_id=employee_id,
                client_id=client_id,
                address_id=address_id,
                total_amount=total_order_amount,
                status='draft', # Используем 'draft'
                payment_status='unpaid',
                amount_paid=0.0,
                due_date=delivery_date + datetime.timedelta(days=7) # Срок оплаты через 7 дней
            ).returning(Order.order_id) # Запрашиваем возврат order_id

            order_insert_result = await session.execute(insert_stmt_order) # Выполняем INSERT
            new_order_id = order_insert_result.scalar_one() # Получаем order_id напрямую
            logging.info(f"Order вставлен с ID: {new_order_id}")

            # 2. Создаем записи в таблице order_lines
            for i, item in enumerate(order_items):
                logging.info(f"Добавляем позицию заказа {i+1}: Product ID {item['product_id']}")
                insert_stmt_order_line = insert(OrderLine).values(
                    order_id=new_order_id, # Используем полученный ID заказа
                    product_id=item['product_id'],
                    quantity=item['quantity'],
                    unit_price=item['unit_price'],
                    # line_total не передаем, т.к. это генерируемый столбец
                )
                await session.execute(insert_stmt_order_line) # Выполняем INSERT для каждой позиции
                logging.info(f"OrderLine {i+1} добавлен в сессию.")

            logging.info("Все OrderLine добавлены в сессию. Выполняем commit.")
            await session.commit() # КОММИТ ТРАНЗАКЦИИ
            logging.info("Транзакция успешно закоммичена.")

            # Формирование подробной сводки заказа
            order_id_escaped = escape_markdown_v2(str(new_order_id))
            client_name_escaped = escape_markdown_v2(client_name)
            delivery_date_str_escaped = escape_markdown_v2(delivery_date.strftime('%d.%m.%Y'))
            total_amount_str_escaped = escape_markdown_v2(str(round(total_order_amount, 2)))

            # Заголовок сводки
            summary_parts = [
                f"✅ *Заказ №{order_id_escaped} успешно оформлен\\!*", "\n",
                f"Клиент: *{client_name_escaped}*", "\n",
                f"Ожидаемая дата доставки: *{delivery_date_str_escaped}*", "\n\n",
                "*Состав заказа:*", "\n"
            ]

            # Детали по каждой позиции
            for i, item in enumerate(order_items):
                product_name_escaped = escape_markdown_v2(item.get('product_name', 'Неизвестный товар'))
                quantity_escaped = escape_markdown_v2(str(item['quantity']))
                unit_price_escaped = escape_markdown_v2(str(round(item['unit_price'], 2)))
                line_total_escaped = escape_markdown_v2(str(round(item['line_total'], 2)))

                summary_parts.append(
                    f"{i+1}\\. {product_name_escaped}\n"
                    f"   Цена: {unit_price_escaped} грн, Количество: {quantity_escaped}, Сумма: {line_total_escaped} грн\n"
                )
            
            summary_parts.append(f"\n*Итого по заказу: {total_amount_str_escaped} грн*\n")
            summary_parts.append("Ожидает подтверждения администратором\\.")

            final_success_message = "".join(summary_parts)

            await callback.message.edit_text(final_success_message, parse_mode="MarkdownV2")
            logging.info("Сообщение об успехе отправлено.")
            await state.clear()
            logging.info("Состояние FSM очищено.")
        except sa_exc.IntegrityError as e:
            logging.error(f"IntegrityError при сохранении заказа: {e}", exc_info=True)
            await session.rollback() # Откат транзакции
            error_message = f"❌ Ошибка целостности данных при создании заказа: {escape_markdown_v2(str(e))}\n" \
                            "Пожалуйста, проверьте данные или обратитесь к администратору."
            await callback.message.edit_text(error_message, parse_mode="MarkdownV2")
            logging.info("Сообщение об ошибке целостности данных отправлено. FSM очищено.")
            await state.clear()
        except Exception as e:
            logging.error(f"Непредвиденная ошибка при сохранении заказа: {e}", exc_info=True)
            await session.rollback() # Откат транзакции
            error_message = f"❌ Произошла непредвиденная ошибка при сохранении заказа: {escape_markdown_v2(str(e))}\n" \
                            "Пожалуйста, попробуйте еще раз или обратитесь к администратору."
            await callback.message.edit_text(error_message, parse_mode="MarkdownV2")
            logging.info("Сообщение о непредвиденной ошибке отправлено. FSM очищено.")
            await state.clear()
    await callback.answer() # Всегда отвечаем на callback_query
    logging.info("Функция confirm_and_save_order завершена.")

@router.callback_query(F.data == "back_to_address_selection")
async def back_to_address_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Возвращает к выбору адреса.
    """
    from handlers.orders.add_addresses_order import send_address_options
    data = await state.get_data()
    client_id = data.get('client_id')
    if client_id:
        await send_address_options(callback, state, client_id, bot)
    else:
        await callback.message.edit_text("Процесс отменен. Клиент не найден. Пожалуйста, начните заново /new_order.")
        await state.clear()
    await callback.answer()