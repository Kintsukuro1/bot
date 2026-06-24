import asyncio
from typing import Tuple
from src.db import add_balance, deduct_balance, transfer_balance, registrar_transaccion

class EconomyService:
    @staticmethod
    async def add_balance(user_id: int, amount: int) -> None:
        """Añade saldo a un usuario de forma asíncrona."""
        await asyncio.to_thread(add_balance, user_id, amount)

    @staticmethod
    async def deduct_balance(user_id: int, amount: int) -> Tuple[bool, int]:
        """Resta saldo a un usuario de forma asíncrona. Retorna (success, nuevo_saldo)."""
        return await asyncio.to_thread(deduct_balance, user_id, amount)

    @staticmethod
    async def transfer_balance(from_user_id: int, to_user_id: int, amount: int, reason: str) -> Tuple[bool, int, int]:
        """Realiza una transferencia de dinero de forma atómica. Retorna (success, saldo_emisor, saldo_receptor)."""
        return await asyncio.to_thread(transfer_balance, from_user_id, to_user_id, amount, reason)

    @staticmethod
    async def log_transaction(user_id: int, amount: int, transaction_type: str) -> None:
        """Registra una transacción en el historial de transacciones."""
        await asyncio.to_thread(registrar_transaccion, user_id, amount, transaction_type)
