import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from middlewares.role_middleware import RoleMiddleware
from states.inventory_states import InventoryReceiptStates
from db.setup import get_db_session
from db.models import Supplier, Product, IncomingDelivery, InventoryMovement, Stock, SupplierInvoice, Employee # Импортируем Employee
from sqlalchemy.future import select
from sqlalchemy import insert, update, exc as sa_exc # Добавляем sa_exc для обработки ошибок SQLAlchemy

# Импортируем хелперы форматирования
from utils.text_formatter import escape_markdown_v2 # Для общего экранирования
from aiogram.utils.markdown import bold, italic # Для жирного и курсива
from aiogram.utils.formatting import Spoiler # Для спойлера, если он нужен

router = Router()

# Применяем RoleMiddleware для команд склада
router.message.middleware(RoleMiddleware(required_roles=['admin', 'manager', 'warehouse']))
router.callback_query.middleware(RoleMiddleware(required_roles=['admin', 'manager', 'warehouse']))

@router.message(Command("add_delivery"))
async def cmd_add_delivery(message: Message, state: FSMContext, user_role: str):
    """
    Начинает процесс добавления поступления товара.
    Предлагает пользователю выбрать поставщика.
    """
    await message.answer(f"Вы {user_role}. Запуск процесса добавления поступления товара.")
    await message.answer("Пожалуйста, выберите поставщика из списка:")

    async for session in get_db_session():
        suppliers_stmt = select(Supplier)
        suppliers_result = await session.execute(suppliers_stmt)
        suppliers = suppliers_result.scalars().all()

        if not suppliers:
            await message.answer("В системе пока нет зарегистрированных поставщиков. Пожалуйста, добавьте их сначала.")
            await state.clear()
            return

        buttons = []
        for supplier in suppliers:
            # ✅ Экранируем имя поставщика для текста кнопки
            button_text = escape_markdown_v2(supplier.name)
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"select_supplier_{supplier.supplier_id}")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer("Список поставщиков:", reply_markup=keyboard, parse_mode="MarkdownV2")
        await state.set_state(InventoryReceiptStates.waiting_for_supplier_selection)


@router.callback_query(InventoryReceiptStates.waiting_for_supplier_selection, F.data.startswith("select_supplier_"))
async def process_supplier_selection(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор поставщика.
    Предлагает выбрать дату накладной.
    """
    supplier_id = int(callback.data.split("_")[-1])
    async for session in get_db_session():
        supplier_stmt = select(Supplier).where(Supplier.supplier_id == supplier_id)
        supplier_result = await session.execute(supplier_stmt)
        supplier = supplier_result.scalar_one_or_none()

        if supplier:
            # Сохраняем ID поставщика и создаем временный список позиций в накладной
            await state.update_data(supplier_id=supplier.supplier_id,
                                    supplier_name=supplier.name,
                                    receipt_items=[]) # Список для хранения {product_id, quantity, unit_cost, line_total}

            # Генерируем кнопки для выбора даты
            today = datetime.date.today()
            buttons = []
            for i in range(-7, 8): # От -7 до +7 дней
                date_to_show = today + datetime.timedelta(days=i)
                # Форматируем дату для отображения и для callback_data
                button_text = date_to_show.strftime("%d.%m.%Y")
                callback_data = f"select_date_{date_to_show.isoformat()}" # ISO формат для удобства парсинга
                buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            # ✅ Изменен edit_text для включения reply_markup
            await callback.message.edit_text(f"Вы выбрали поставщика: {bold(escape_markdown_v2(supplier.name))}\n"
                                             "Теперь, пожалуйста, выберите дату накладной:",
                                             reply_markup=keyboard, # Передаем клавиатуру здесь
                                             parse_mode="MarkdownV2")
            await state.set_state(InventoryReceiptStates.waiting_for_invoice_date)
        else:
            await callback.answer("Ошибка: Поставщик не найден. Пожалуйста, попробуйте еще раз.", show_alert=True)
            await state.clear() # Сбросим FSM
            await callback.message.edit_text("Процесс отменен. Пожалуйста, начните заново /add_delivery.")
    await callback.answer() # Всегда отвечаем на callback_query


@router.callback_query(InventoryReceiptStates.waiting_for_invoice_date, F.data.startswith("select_date_"))
async def process_invoice_date_selection(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор даты накладной.
    Запрашивает номер накладной.
    """
    invoice_date_str = callback.data.split("_")[-1]
    try:
        invoice_date = datetime.date.fromisoformat(invoice_date_str)
    except ValueError:
        await callback.answer("Ошибка: Некорректный формат даты. Пожалуйста, попробуйте еще раз.", show_alert=True)
        return

    await state.update_data(invoice_date=invoice_date)
    await callback.message.edit_text(f"Дата накладной: {bold(invoice_date.strftime('%d.%m.%Y'))}\n"
                                     "Теперь, пожалуйста, введите номер накладной от поставщика:",
                                     parse_mode="MarkdownV2")
    await state.set_state(InventoryReceiptStates.waiting_for_invoice_number)
    await callback.answer()


@router.message(InventoryReceiptStates.waiting_for_invoice_number, F.text)
async def process_invoice_number(message: Message, state: FSMContext):
    """
    Обрабатывает ввод номера накладной.
    Предлагает пользователю выбрать товар.
    """
    invoice_number = message.text.strip()
    if not invoice_number:
        await message.answer("Номер накладной не может быть пустым. Пожалуйста, введите корректный номер:")
        return

    await state.update_data(invoice_number=invoice_number)
    await message.answer(f"Номер накладной: {bold(escape_markdown_v2(invoice_number))}\n"
                         "Теперь, пожалуйста, выберите товар для добавления:",
                         parse_mode="MarkdownV2")

    async for session in get_db_session():
        products_stmt = select(Product)
        products_result = await session.execute(products_stmt)
        products = products_result.scalars().all()

        if not products:
            await message.answer("В системе пока нет зарегистрированных товаров. Пожалуйста, добавьте их сначала.")
            await state.clear()
            return

        buttons = []
        for product in products:
            # ✅ КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: Экранируем ВСЮ строку текста кнопки.
            button_text = escape_markdown_v2(f"{product.name} ({product.price} грн)")
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"select_product_add_{product.product_id}")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        # ✅ Для этого сообщения parse_mode="MarkdownV2" должен быть установлен
        await message.answer("Список товаров (для выбора):", reply_markup=keyboard)
        await state.set_state(InventoryReceiptStates.waiting_for_product_selection)


@router.callback_query(InventoryReceiptStates.waiting_for_product_selection, F.data.startswith("select_product_add_"))
async def process_product_selection(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор товара.
    Запрашивает количество товара.
    """
    product_id = int(callback.data.split("_")[-1])
    async for session in get_db_session():
        product_stmt = select(Product).where(Product.product_id == product_id)
        product_result = await session.execute(product_stmt)
        product = product_result.scalar_one_or_none()

        if product:
            await state.update_data(current_product_id=product.product_id,
                                    current_product_name=product.name)
            await callback.message.edit_text(f"Вы выбрали товар: {bold(escape_markdown_v2(product.name))}\n"
                                             "Пожалуйста, введите количество товара:",
                                             parse_mode="MarkdownV2")
            await state.set_state(InventoryReceiptStates.waiting_for_product_quantity)
        else:
            await callback.answer("Ошибка: Товар не найден. Пожалуйста, попробуйте еще раз.", show_alert=True)
            # Возвращаемся к выбору товара
            await callback.message.edit_text("Пожалуйста, выберите товар для добавления:")
            async for s_session in get_db_session(): # Используем новую сессию для надежности
                products_stmt = select(Product)
                products_result = await s_session.execute(products_stmt)
                products = products_result.scalars().all()
                buttons = []
                for p in products:
                    button_text = escape_markdown_v2(f"{p.name} ({p.price} грн)")
                    buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"select_product_add_{p.product_id}")])
                keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
                await callback.message.edit_reply_markup(reply_markup=keyboard) # Обновляем только клавиатуру
            await state.set_state(InventoryReceiptStates.waiting_for_product_selection)
    await callback.answer()


@router.message(InventoryReceiptStates.waiting_for_product_quantity, F.text)
async def process_product_quantity(message: Message, state: FSMContext):
    """
    Обрабатывает ввод количества товара.
    Запрашивает себестоимость единицы товара.
    """
    try:
        # ✅ Учитываем, что количество может быть дробным, поэтому Float
        quantity = float(message.text.strip().replace(',', '.'))
        if quantity <= 0:
            await message.answer("Количество должно быть положительным числом. Пожалуйста, введите корректное количество:")
            return
    except ValueError:
        await message.answer("Пожалуйста, введите корректное числовое значение для количества.")
        return

    await state.update_data(current_quantity=quantity)
    await message.answer(f"Количество: {bold(str(quantity))}\n"
                         f"Теперь, пожалуйста, введите себестоимость за единицу товара {escape_markdown_v2('(например, 123.45)')}:", # <--- Экранируем "(например, 123.45)"
                         parse_mode="MarkdownV2")
    await state.set_state(InventoryReceiptStates.waiting_for_unit_cost)


@router.message(InventoryReceiptStates.waiting_for_unit_cost, F.text)
async def process_unit_cost(message: Message, state: FSMContext):
    """
    Обрабатывает ввод себестоимости.
    Предлагает добавить еще товар или завершить поступление.
    """
    try:
        # ✅ Учитываем, что себестоимость может быть дробной, поэтому Float
        unit_cost = float(message.text.strip().replace(',', '.'))
        if unit_cost < 0: # Себестоимость может быть 0, но не отрицательной
            await message.answer("Себестоимость не может быть отрицательной. Пожалуйста, введите корректную себестоимость:")
            return
    except ValueError:
        await message.answer("Пожалуйста, введите корректное числовое значение для себестоимости.")
        return

    data = await state.get_data()
    current_product_id = data['current_product_id']
    current_product_name = data['current_product_name']
    quantity = data['current_quantity']

    line_total = quantity * unit_cost

    # Добавляем позицию в список receipt_items
    receipt_items = data.get('receipt_items', [])
    receipt_items.append({
        'product_id': current_product_id,
        'product_name': current_product_name,
        'quantity': quantity,
        'unit_cost': unit_cost,
        'line_total': line_total
    })
    await state.update_data(receipt_items=receipt_items)

    # Формируем текущую сводку по накладной
    summary_text = f"{bold('Текущая позиция добавлена:')}\n" \
                   f"  Товар: {bold(escape_markdown_v2(current_product_name))}\n" \
                   f"  Количество: {bold(str(quantity))}\n" \
                   f"  Себестоимость/ед: {bold(str(unit_cost))} грн\n" \
                   f"  Сумма по позиции: {bold(str(round(line_total, 2)))} грн\n\n" \
                   f"{bold('Всего позиций в накладной:')} {bold(str(len(receipt_items)))}\n" \
                   f"{bold('Общая сумма накладной:')} {bold(str(round(sum(item['line_total'] for item in receipt_items), 2)))} грн\n\n" \
                   "Что дальше?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить еще товар", callback_data="add_another_product")],
        [InlineKeyboardButton(text="✅ Завершить поступление", callback_data="complete_receipt")],
        # [InlineKeyboardButton(text="✏️ Редактировать накладную", callback_data="edit_receipt")] # Пока не реализуем
    ])

    await message.answer(summary_text, reply_markup=keyboard, parse_mode="MarkdownV2")
    await state.set_state(InventoryReceiptStates.confirming_line_item)


@router.callback_query(InventoryReceiptStates.confirming_line_item, F.data == "add_another_product")
async def add_another_product(callback: CallbackQuery, state: FSMContext):
    """
    Пользователь решил добавить еще один товар в текущую накладную.
    Возвращаемся к выбору товара.
    """
    await callback.message.edit_text("Пожалуйста, выберите следующий товар для добавления:")
    async for session in get_db_session():
        products_stmt = select(Product)
        products_result = await session.execute(products_stmt)
        products = products_result.scalars().all()

        buttons = []
        for product in products:
            # ✅ КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: Экранируем ВСЮ строку текста кнопки.
            button_text = escape_markdown_v2(f"{product.name} ({product.price} грн)")
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"select_product_add_{product.product_id}")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        # Обратите внимание, что здесь edit_reply_markup, а не edit_text, чтобы обновить только клавиатуру
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    await state.set_state(InventoryReceiptStates.waiting_for_product_selection)
    await callback.answer()


@router.callback_query(InventoryReceiptStates.confirming_line_item, F.data == "complete_receipt")
async def complete_receipt(callback: CallbackQuery, state: FSMContext):
    """
    Пользователь решил завершить поступление.
    Сохраняем данные в базу данных и выводим сводку.
    """
    data = await state.get_data()
    supplier_id = data.get('supplier_id')
    supplier_name = data.get('supplier_name')
    invoice_date = data.get('invoice_date')
    invoice_number = data.get('invoice_number')
    receipt_items = data.get('receipt_items', [])
    user_telegram_id = callback.from_user.id

    if not receipt_items:
        await callback.message.edit_text("Накладная пуста. Пожалуйста, добавьте хотя бы одну позицию.")
        await state.clear()
        await callback.answer()
        return

    total_receipt_amount = sum(item['line_total'] for item in receipt_items)

    # Формируем окончательную сводку для подтверждения
    final_summary_text = f"{bold('Сводка поступления:')}\n\n" \
                         f"Поставщик: {bold(escape_markdown_v2(supplier_name))}\n" \
                         f"Дата накладной: {bold(invoice_date.strftime('%d.%m.%Y'))}\n" \
                         f"Номер накладной: {bold(escape_markdown_v2(invoice_number))}\n\n" \
                         f"{bold('Позиции:')}\n"

    for i, item in enumerate(receipt_items):
        final_summary_text += (
            f"{i+1}\\. " # Экранируем точку после номера позиции
            f"{escape_markdown_v2(item['product_name'])}: "
            f"{escape_markdown_v2(str(item['quantity']))} шт\\. x " # Экранируем точку в количестве (если float)
            f"{escape_markdown_v2(str(item['unit_cost']))} грн \\= " # <--- ИСПРАВЛЕНИЕ ЗДЕСЬ: Экранируем =
            f"{escape_markdown_v2(str(round(item['line_total'], 2)))} грн\n" # Экранируем точку в общей сумме позиции
        )

    final_summary_text += f"\n{bold('Общая сумма поступления:')} {bold(escape_markdown_v2(str(round(total_receipt_amount, 2))))} грн"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить и сохранить", callback_data="confirm_save_receipt")],
        [InlineKeyboardButton(text="❌ Отменить поступление", callback_data="cancel_receipt")]
    ])

    await callback.message.edit_text(final_summary_text, reply_markup=keyboard, parse_mode="MarkdownV2")
    await state.set_state(InventoryReceiptStates.confirming_receipt)
    await callback.answer()


@router.callback_query(InventoryReceiptStates.confirming_receipt, F.data == "confirm_save_receipt")
async def confirm_save_receipt(callback: CallbackQuery, state: FSMContext):
    """
    Сохраняет все данные поступления в базу данных.
    """
    data = await state.get_data()
    supplier_id = data.get('supplier_id')
    supplier_name = data.get('supplier_name')
    invoice_date = data.get('invoice_date')
    invoice_number = data.get('invoice_number')
    receipt_items = data.get('receipt_items', [])
    user_telegram_id = callback.from_user.id # ID сотрудника

    total_receipt_amount = sum(item['line_total'] for item in receipt_items)

    async for session in get_db_session():
        try:
            # 1. Создаем/обновляем счет поставщика (SupplierInvoice)
            supplier_invoice_stmt = select(SupplierInvoice).where(
                SupplierInvoice.supplier_id == supplier_id,
                SupplierInvoice.invoice_number == invoice_number
            )
            supplier_invoice_result = await session.execute(supplier_invoice_stmt)
            supplier_invoice = supplier_invoice_result.scalar_one_or_none()

            if supplier_invoice:
                supplier_invoice.total_amount += total_receipt_amount
                supplier_invoice.payment_status = 'unpaid'
            else:
                supplier_invoice = SupplierInvoice(
                    supplier_id=supplier_id,
                    invoice_number=invoice_number,
                    invoice_date=invoice_date,
                    total_amount=total_receipt_amount,
                    amount_paid=0.0,
                    payment_status='unpaid',
                    created_at=datetime.datetime.now()
                )
                session.add(supplier_invoice)
            await session.flush() # Получаем supplier_invoice_id

            # 2. Обновляем остатки на складе и создаем движения товара
            for item in receipt_items:
                product_id = item['product_id']
                quantity = item['quantity']
                unit_cost = item['unit_cost']
                line_total = item['line_total']

                # Создаем запись о входящей поставке для каждой позиции
                item_delivery = IncomingDelivery(
                    supplier_id=supplier_id,
                    delivery_date=invoice_date,
                    product_id=product_id,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    total_cost=line_total,
                    supplier_invoice_id=supplier_invoice.supplier_invoice_id # ИСПРАВЛЕНО: использование supplier_invoice_id
                )
                session.add(item_delivery)
                await session.flush()

                # Обновляем Stock
                stock_entry_stmt = select(Stock).where(Stock.product_id == product_id)
                stock_entry_result = await session.execute(stock_entry_stmt)
                stock_entry = stock_entry_result.scalar_one_or_none()

                if stock_entry:
                    stock_entry.quantity += quantity

                else:
                    new_stock_entry = Stock(
                        product_id=product_id,
                        quantity=quantity,

                    )
                    session.add(new_stock_entry)

                # Создаем InventoryMovement
                new_movement = InventoryMovement(
                    product_id=product_id,
                    quantity_change=quantity,
                    movement_type='incoming',
                    movement_date=datetime.datetime.now(),
                    unit_cost=unit_cost,
                    source_document_type='delivery',
                    source_document_id=item_delivery.delivery_id,
                    description=f"Поступление от поставщика {escape_markdown_v2(supplier_name)}, накладная {escape_markdown_v2(invoice_number)}" # Экранируем имена в описании
                )
                session.add(new_movement)

            await session.commit()

            # ✅ ИСПРАВЛЕНИЕ: Удаляем parse_mode="MarkdownV2" из сообщения об успехе
            invoice_date_str_escaped = escape_markdown_v2(invoice_date.strftime('%d.%m.%Y'))
            total_amount_str_escaped = escape_markdown_v2(str(round(total_receipt_amount, 2)))

            final_success_message = "".join([
                '✅ Поступление успешно оформлено!', "\n", # Убрали bold(), т.к. нет parse_mode
                "Накладная №", escape_markdown_v2(invoice_number),
                " от ", invoice_date_str_escaped,
                " на сумму ", total_amount_str_escaped, " грн сохранена."
            ])

            # Отправляем как обычный текст, без MarkdownV2 парсинга
            await callback.message.edit_text(final_success_message) # <--- УДАЛЕНО: parse_mode="MarkdownV2"
            await state.clear()
        except sa_exc.IntegrityError as e:
            await session.rollback()
            error_details = escape_markdown_v2(str(e))
            error_message = "".join([ # Собираем в строку
                '❌ Ошибка целостности данных (возможно, дубликат номера накладной):', "\n", # Убрали bold()
                f"{error_details}\n",
                escape_markdown_v2('Пожалуйста, проверьте номер накладной или обратитесь к администратору.')
            ])
            # Отправляем как обычный текст
            await callback.message.edit_text(error_message) # <--- УДАЛЕНО: parse_mode="MarkdownV2"
            print(f"Ошибка целостности данных: {e}")
            await state.clear()
        except Exception as e:
            await session.rollback()
            error_details = escape_markdown_v2(str(e))
            error_message = "".join([ # Собираем в строку
                '❌ Произошла непредвиденная ошибка при сохранении поступления:', "\n", # Убрали bold()
                f"{error_details}\n",
                escape_markdown_v2('Пожалуйста, попробуйте еще раз или обратитесь к администратору.')
            ])
            # Отправляем как обычный текст
            await callback.message.edit_text(error_message) # <--- УДАЛЕНО: parse_mode="MarkdownV2"
            print(f"Непредвиденная ошибка при сохранении поступления: {e}")
            await state.clear()
    await callback.answer()


@router.callback_query(InventoryReceiptStates.confirming_receipt, F.data == "cancel_receipt")
async def cancel_receipt(callback: CallbackQuery, state: FSMContext):
    """
    Отменяет процесс поступления товара.
    """
    await state.clear()
    await callback.message.edit_text(f"{bold('❌ Поступление отменено.')}", parse_mode="MarkdownV2")
    await callback.answer()