# handlers/orders/add_addresses_order.py

import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from middlewares.role_middleware import RoleMiddleware
from states.order_states import OrderCreationStates
from db.setup import get_db_session
from db.models import Client, Address
from sqlalchemy.future import select
from utils.text_formatter import escape_markdown_v2, bold, italic

router = Router()

router.message.middleware(RoleMiddleware(required_roles=['admin', 'manager']))
router.callback_query.middleware(RoleMiddleware(required_roles=['admin', 'manager']))

async def send_address_options(callback: CallbackQuery, state: FSMContext, client_id: int, bot: Bot):
    """
    Отправляет варианты выбора адреса для клиента: существующие или новый.
    Если адрес один - подставляет автоматически и переходит к выбору продукта.
    """
    async for session in get_db_session():
        addresses_stmt = select(Address).where(Address.client_id == client_id)
        addresses_result = await session.execute(addresses_stmt)
        addresses = addresses_result.scalars().all()

        if len(addresses) == 1:
            # ✅ НОВАЯ ЛОГИКА: Если адрес только один, подставляем его автоматически
            single_address = addresses[0]
            await state.update_data(address_id=single_address.address_id, address_text=single_address.address_text)
            
            await callback.message.edit_text(f"Автоматически выбран адрес: {bold(escape_markdown_v2(single_address.address_text))}\n"
                                             "Теперь добавьте товары в заказ:",
                                             parse_mode="MarkdownV2")
            
            # Переходим к обработчику добавления товаров
            from handlers.orders.add_product_order import send_product_options
            # Вызываем send_product_options, передавая ей текущий callback и state, а также bot
            await send_product_options(callback, state, bot) # Передаем 'bot'
            
            await callback.answer() # Важно ответить на callback_query
            return # Завершаем выполнение функции здесь

        # ✅ СУЩЕСТВУЮЩАЯ ЛОГИКА: Если адресов несколько или нет ни одного
        buttons = []
        if addresses:
            for addr in addresses:
                button_text = escape_markdown_v2(addr.address_text)
                buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"select_address_{addr.address_id}")])
            buttons.append([InlineKeyboardButton(text="🆕 Добавить новый адрес", callback_data="add_new_address")])
        else:
            # Если адресов нет вообще
            await callback.message.edit_text("У этого клиента нет зарегистрированных адресов.\n"
                                             "Пожалуйста, добавьте новый адрес доставки:",
                                             parse_mode="MarkdownV2")
            await state.set_state(OrderCreationStates.waiting_for_new_address_input)
            await callback.answer()
            return # Завершаем выполнение, ожидая ввода нового адреса

        buttons.append([InlineKeyboardButton(text="↩️ Назад к выбору клиента", callback_data="back_to_client_selection")])
        buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order_creation")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        if isinstance(callback, CallbackQuery):
            await callback.message.edit_text("Выберите существующий адрес или добавьте новый:", reply_markup=keyboard, parse_mode="MarkdownV2")
        else:
            await bot.send_message(callback.chat.id, "Выберите существующий адрес или добавьте новый:", reply_markup=keyboard, parse_mode="MarkdownV2")

        await state.set_state(OrderCreationStates.waiting_for_address_selection)
    await callback.answer() # Важно ответить на callback_query


@router.callback_query(OrderCreationStates.waiting_for_address_selection, F.data.startswith("select_address_"))
async def process_address_selection(callback: CallbackQuery, state: FSMContext, bot: Bot): # Добавил bot
    """
    Обрабатывает выбор существующего адреса.
    Сохраняет ID адреса и переходит к выбору товаров.
    """
    address_id = int(callback.data.split("_")[-1])
    async for session in get_db_session():
        address_stmt = select(Address).where(Address.address_id == address_id)
        address_result = await session.execute(address_stmt)
        address = address_result.scalar_one_or_none()

        if address:
            await state.update_data(address_id=address.address_id, address_text=address.address_text)
            await callback.message.edit_text(f"Выбран адрес: {bold(escape_markdown_v2(address.address_text))}\n"
                                             "Теперь добавьте товары в заказ:",
                                             parse_mode="MarkdownV2")
            # Переходим к обработчику добавления товаров
            from handlers.orders.add_product_order import send_product_options
            await send_product_options(callback, state, bot) # Передаем 'bot'
        else:
            await callback.answer("Ошибка: Адрес не найден. Пожалуйста, попробуйте еще раз.", show_alert=True)
            # Повторно отправляем варианты адреса
            data = await state.get_data()
            client_id = data.get('client_id')
            if client_id:
                await send_address_options(callback, state, client_id, bot) # Передаем 'bot'
            else:
                await callback.message.edit_text("Процесс отменен. Клиент не найден. Пожалуйста, начните заново /new_order.")
                await state.clear()
    await callback.answer()


@router.callback_query(OrderCreationStates.waiting_for_address_selection, F.data == "add_new_address")
async def cmd_add_new_address(callback: CallbackQuery, state: FSMContext):
    """
    Запрашивает у пользователя ввод нового адреса.
    """
    await callback.message.edit_text("Пожалуйста, введите новый адрес доставки:")
    await state.set_state(OrderCreationStates.waiting_for_new_address_input)
    await callback.answer()

@router.message(OrderCreationStates.waiting_for_new_address_input, F.text)
async def process_new_address_input(message: Message, state: FSMContext, bot: Bot): # Добавил bot
    """
    Обрабатывает ввод нового адреса, сохраняет его и переходит к выбору товаров.
    """
    new_address_text = message.text.strip()
    if not new_address_text:
        await message.answer("Адрес не может быть пустым. Пожалуйста, введите корректный адрес:")
        return

    data = await state.get_data()
    client_id = data.get('client_id')

    if not client_id:
        await message.answer("Ошибка: Клиент не определен. Пожалуйста, начните заново /new_order.")
        await state.clear()
        return

    async for session in get_db_session():
        try:
            new_address = Address(
                client_id=client_id,
                address_text=new_address_text
            )
            session.add(new_address)
            await session.flush() # Получаем address_id
            await session.commit()

            await state.update_data(address_id=new_address.address_id, address_text=new_address.address_text)
            await message.answer(f"Новый адрес добавлен: {bold(escape_markdown_v2(new_address_text))}\n"
                                 "Теперь добавьте товары в заказ:",
                                 parse_mode="MarkdownV2")
            # Переходим к обработчику добавления товаров
            from handlers.orders.add_product_order import send_product_options
            # Вызываем send_product_options, передавая message.bot
            await send_product_options(message, state, bot) # Передаем 'bot'
        except Exception as e:
            await session.rollback()
            await message.answer(f"{bold('❌ Произошла ошибка при добавлении нового адреса:')}\n"
                                 f"{escape_markdown_v2(str(e))}\n"
                                 "Пожалуйста, попробуйте еще раз.",
                                 parse_mode="MarkdownV2")
            print(f"Ошибка при добавлении нового адреса: {e}")


@router.callback_query(F.data == "back_to_client_selection")
async def back_to_client_selection(callback: CallbackQuery, state: FSMContext, bot: Bot): # Добавил bot
    """
    Возвращает к выбору клиента.
    """
    from handlers.orders.add_client_order import cmd_new_order # Перезапускаем выбор клиента
    # cmd_new_order ожидает Message, state, user_role. Здесь у нас callback.message
    # user_role нужно получить из state.data, т.к. middleware уже отработал
    data = await state.get_data()
    user_role = data.get('user_role', 'client') # Получаем роль из FSM-контекста, по умолчанию 'client'
    
    await cmd_new_order(callback.message, state, user_role)
    await callback.answer()