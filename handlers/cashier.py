# handlers/cashier.py
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from middlewares.role_middleware import RoleMiddleware

router = Router()

# Применяем RoleMiddleware для команд кассира
router.message.middleware(RoleMiddleware(required_roles=['admin', 'cashier']))
router.callback_query.middleware(RoleMiddleware(required_roles=['admin', 'cashier']))


@router.message(Command("payments"))
async def cmd_payments(message: Message, user_role: str):
    """
    Обработчик команды /payments.
    """
    await message.answer(f"Вы {user_role}. Запуск модуля приема оплат клиентов...")
    # Здесь будет FSM для приема оплат

@router.message(Command("financial_report_today"))
async def cmd_financial_report_today(message: Message, user_role: str):
    """
    Обработчик команды /financial_report_today.
    """
    await message.answer(f"Вы {user_role}. Формирую отчет об оплатах за сегодня...")
    # Здесь будет логика для отчета

@router.message(Command("cash_balance"))
async def cmd_cash_balance(message: Message, user_role: str):
    """
    Обработчик команды /cash_balance.
    """
    await message.answer(f"Вы {user_role}. Показываю остаток по кассе...")
    # Здесь будет логика для остатка по кассе

@router.message(Command("accounts_receivable"))
async def cmd_accounts_receivable(message: Message, user_role: str):
    """
    Обработчик команды /accounts_receivable.
    """
    await message.answer(f"Вы {user_role}. Формирую отчет по дебиторской задолженности...")
    # Здесь будет логика для отчета по дебиторке