# middlewares/role_middleware.py

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Dict, Any
from db.setup import get_db_session
from db.models import Employee # <-- ИЗМЕНЕНО: Импортируем Employee вместо User
from sqlalchemy.future import select

class RoleMiddleware(BaseMiddleware):
    def __init__(self, required_roles: list = None):
        self.required_roles = required_roles
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Any],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        async for session in get_db_session():
            # <--- Вот здесь должно быть Employee.id_telegram
            stmt = select(Employee).where(Employee.id_telegram == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                # Если пользователя нет в БД, возможно, это новый клиент
                # Можно создать его с ролью 'client' или отказать в доступе
                await event.answer("Вы не зарегистрированы в системе. Пожалуйста, обратитесь к администратору.")
                return

            data['user_role'] = user.role # Передаем роль в хэндлер
            data['db_user'] = user # Передаем объект пользователя в хэндлер

            if self.required_roles and user.role not in self.required_roles:
                await event.answer("У вас нет прав для выполнения этой операции.")
                return

        return await handler(event, data)