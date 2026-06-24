import asyncio
from src.db import ensure_user, get_balance

class UserService:
    @staticmethod
    async def ensure_user(user_id: int, user_name: str = None) -> None:
        """Asegura que el usuario existe en la base de datos."""
        await asyncio.to_thread(ensure_user, user_id, user_name)

    @staticmethod
    async def get_balance(user_id: int) -> int:
        """Obtiene el saldo actual de un usuario de forma asíncrona."""
        return await asyncio.to_thread(get_balance, user_id)
