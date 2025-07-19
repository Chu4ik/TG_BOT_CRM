import asyncio # Убедитесь, что этот импорт есть, если используете asyncio.sleep (но мы их уберем в финале)
import datetime # Убедитесь, что этот импорт есть
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from middlewares.role_middleware import RoleMiddleware
from states.order_states import OrderCreationStates
from db.setup import get_db_session
from db.models import Client
from sqlalchemy.future import select
from utils.text_formatter import escape_markdown_v2, bold, italic

router = Router()

# Убедитесь, что RoleMiddleware раскомментирована и активна
router.message.middleware(RoleMiddleware(required_roles=['admin', 'manager']))
router.callback_query.middleware(RoleMiddleware(required_roles=['admin', 'manager']))


@router.message(Command("new_order"))
async def cmd_new_order(message: Message, state: FSMContext, user_role: str):
    """
    Начинает процесс создания нового заказа.
    Запрашивает у пользователя ввод имени клиента для поиска.
    """
    # Первое сообщение (приветствие с ролью). Мы его возвращаем, так как оно информативное.
    await message.answer(f"Вы {user_role}. Запуск процесса создания нового заказа.")

    # ✅ Убираем диагностические паузы, они больше не нужны
    # await asyncio.sleep(0.1)

    # Второе сообщение с основным запросом
    await message.answer("Пожалуйста, начните вводить имя клиента для поиска:")

    # ✅ Убираем диагностические паузы, они больше не нужны
    # await asyncio.sleep(0.1)

    # Третье сообщение с кнопкой отмены (клавиатура)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить создание заказа", callback_data="cancel_order_creation")]
    ])
    # parse_mode не указываем, так как это текст кнопки.
    await message.answer("Или отмените:", reply_markup=keyboard)

    # ✅ Ключевой шаг: устанавливаем состояние FSM для перехода к обработке ввода имени клиента.
    await state.set_state(OrderCreationStates.waiting_for_client_selection)

# Ниже идет функция process_client_name_search, которая будет обрабатывать
# текстовый ввод, когда пользователь находится в состоянии waiting_for_client_selection.

@router.message(OrderCreationStates.waiting_for_client_selection, F.text)
async def process_client_name_search(message: Message, state: FSMContext):
    """
    Обрабатывает ввод имени клиента для поиска.
    Выводит ограниченный список найденных клиентов в виде кнопок.
    """
    search_query = message.text.strip()
    if not search_query:
        await message.answer("Запрос не может быть пустым. Пожалуйста, введите имя клиента:")
        return

    async for session in get_db_session():
        clients_stmt = select(Client).where(Client.name.ilike(f"%{search_query}%")).limit(15)
        clients_result = await session.execute(clients_stmt)
        clients = clients_result.scalars().all()

        if not clients:
            await message.answer(f"Клиенты по запросу '{escape_markdown_v2(search_query)}' не найдены. Попробуйте другой запрос или /new_order для начала.",
                                 parse_mode="MarkdownV2")
            return

        buttons = []
        for client in clients:
            button_text = escape_markdown_v2(client.name)
            buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"select_client_{client.client_id}")])

        buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order_creation")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        # Для этого сообщения parse_mode="MarkdownV2" не указываем.
        await message.answer("Найденные клиенты. Выберите одного:", reply_markup=keyboard)


@router.callback_query(OrderCreationStates.waiting_for_client_selection, F.data.startswith("select_client_"))
async def process_client_selection(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Обрабатывает выбор клиента.
    Сохраняет ID клиента и переходит к выбору адреса.
    """
    client_id = int(callback.data.split("_")[-1])
    async for session in get_db_session():
        client_stmt = select(Client).where(Client.client_id == client_id)
        client_result = await session.execute(client_stmt)
        client = client_result.scalar_one_or_none()

        if client:
            await state.update_data(client_id=client.client_id, client_name=client.name, order_items=[]) # Инициализируем order_items
            await callback.message.edit_text(f"Вы выбрали клиента: {bold(escape_markdown_v2(client.name))}\n"
                                             "Теперь выберите адрес доставки:",
                                             parse_mode="MarkdownV2")
            # Вызываем send_address_options из add_addresses_order.py
            from handlers.orders.add_addresses_order import send_address_options
            await send_address_options(callback, state, client.client_id, bot)
        else:
            await callback.answer("Ошибка: Клиент не найден. Пожалуйста, попробуйте еще раз.", show_alert=True)
            # Возвращаемся к началу выбора клиента
            await callback.message.edit_text("Процесс отменен. Пожалуйста, начните /new_order для выбора клиента.")
            await state.clear()
    await callback.answer()

@router.callback_query(F.data == "cancel_order_creation")
async def cancel_order_creation(callback: CallbackQuery, state: FSMContext):
    """
    Отменяет процесс создания заказа на любом этапе.
    """
    await state.clear()
    await callback.message.edit_text(f"{bold('❌ Создание заказа отменено.')}", parse_mode="MarkdownV2")
    await callback.answer()