# main.py
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.strategy import FSMStrategy
from aiogram.types import BotCommand


from config import settings
from db.setup import engine # Correct for engine
from db.models import Base  # CORRECT for Base (Base is defined in models.py)
from handlers import common, admin, manager, cashier, inventory_add
from handlers.orders import add_client_order # Импортируем отдельные роутеры из handlers.orders
from handlers.orders import add_addresses_order
from handlers.orders import add_product_order
from handlers.orders import add_datedeliveries_order
from handlers.orders import edit_order
from middlewares.role_middleware import RoleMiddleware

logging.basicConfig(level=logging.DEBUG) # <--- ИЗМЕНЕНО: level=logging.DEBUG

# Добавьте логирование для aiohttp.client и aiogram на уровень DEBUG
logging.getLogger('aiohttp.client').setLevel(logging.DEBUG)
logging.getLogger('aiogram').setLevel(logging.DEBUG)
# SQLAlchemy можно оставить на INFO, если не нужно много SQL-логов
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# Функция для установки команд главного меню
async def set_main_menu_commands(bot: Bot):
    """
    Устанавливает команды для бокового меню (меню-гамбургера).
    """
    commands = [
        BotCommand(command="/new_order", description="📝 Создать новый заказ"), # Иконка карандаша/блокнота
        BotCommand(command="/my_orders", description="📦 Мои заказы"),         # Иконка коробки/посылки
        BotCommand(command="/edit_order_admin", description="✍️ Редактировать заказ (Админ)"), # Иконка письма с ручкой
        BotCommand(command="/show_unconfirmed_orders", description="📋 Показать черновики заказов"), # Иконка списка/блокнота
        BotCommand(command="/sales_manager", description="📈 Продажи по менеджерам"), # Иконка графика роста

        BotCommand(command="/payments", description="💳 Принять оплату"),       # Иконка кредитной карты
        BotCommand(command="/financial_report_today", description="💰 Отчет об оплатах за сегодня"), # Иконка мешка денег/монеток
        BotCommand(command="/cash_balance", description="💲 Остаток по кассе"),   # Иконка доллара/денежного мешка
        BotCommand(command="/accounts_receivable", description="📊 Дебиторская задолженность"), # Иконка гистограммы

        BotCommand(command="/add_delivery", description="🚚 Добавить поступление товара"), # Иконка грузовика
        BotCommand(command="/adjust_inventory", description="🗄️ Корректировка по складу"), # Иконка картотеки/шкафа
        BotCommand(command="/inventory_report", description="🔍 Отчет об остатках товара"), # Иконка лупы/поиска
    ]
    await bot.set_my_commands(commands)

async def main():
    # Настройка логирования
    logging.basicConfig(level=logging.INFO)

    # Инициализация бота и диспетчера
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage(), fsm_strategy=FSMStrategy.CHAT)

    # Регистрация middlewares
    dp.message.middleware(RoleMiddleware())
    dp.callback_query.middleware(RoleMiddleware())

    # Регистрация роутеров (хэндлеров)
    dp.include_router(common.router)
    dp.include_router(admin.router)
    dp.include_router(manager.router)
    dp.include_router(cashier.router)
    dp.include_router(inventory_add.router)
    dp.include_router(add_client_order.router)
    dp.include_router(add_addresses_order.router)
    dp.include_router(add_product_order.router)
    dp.include_router(add_datedeliveries_order.router)
    dp.include_router(edit_order.router)

    # Создание таблиц, если их нет (только для первого запуска или если вы меняете схемы)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Установка команд главного меню
    await set_main_menu_commands(bot)

    # Запуск бота
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())