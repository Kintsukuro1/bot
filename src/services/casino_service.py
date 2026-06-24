import asyncio
from typing import Tuple
from src.db import add_balance, deduct_balance, registrar_transaccion, record_game_result

class CasinoService:
    @staticmethod
    async def place_bet(user_id: int, amount: int, game_type: str) -> Tuple[bool, int]:
        """Realiza la deducción del saldo para una apuesta de casino."""
        success, new_balance = await asyncio.to_thread(deduct_balance, user_id, amount)
        if success:
            await asyncio.to_thread(registrar_transaccion, user_id, -amount, f"Apuesta en {game_type}")
        return success, new_balance

    @staticmethod
    async def settle_win(user_id: int, bet_amount: int, winnings: int, game_type: str, difficulty_modifier: float, current_balance: int) -> int:
        """Procesa una victoria en el casino: acredita el premio y registra estadísticas."""
        profit = winnings - bet_amount
        # Winnings es el dinero retornado total (incluye apuesta). Si el juego es 1:1, winnings = bet * 2, profit = bet.
        await asyncio.to_thread(add_balance, user_id, winnings)
        nuevo_saldo = current_balance + winnings
        
        await asyncio.to_thread(registrar_transaccion, user_id, profit, f"{game_type.capitalize()}: Ganó partida")
        await asyncio.to_thread(record_game_result, user_id, game_type, bet_amount, 'win', profit, difficulty_modifier, nuevo_saldo)
        return nuevo_saldo

    @staticmethod
    async def settle_loss(user_id: int, bet_amount: int, game_type: str, difficulty_modifier: float, current_balance: int) -> int:
        """Procesa una derrota en el casino: registra estadísticas y logs correspondientes."""
        nuevo_saldo = current_balance # El saldo ya fue descontado en place_bet
        await asyncio.to_thread(registrar_transaccion, user_id, -bet_amount, f"{game_type.capitalize()}: Perdió partida")
        await asyncio.to_thread(record_game_result, user_id, game_type, bet_amount, 'loss', 0, difficulty_modifier, nuevo_saldo)
        return nuevo_saldo

    @staticmethod
    async def refund_bet(user_id: int, amount: int, game_type: str, reason: str) -> int:
        """Devuelve el dinero de una apuesta en caso de timeout o cancelación del juego."""
        await asyncio.to_thread(add_balance, user_id, amount)
        await asyncio.to_thread(registrar_transaccion, user_id, amount, f"Reembolso {game_type}: {reason}")
        # Obtener nuevo saldo actualizado tras el reembolso
        from src.db import get_balance
        nuevo_saldo = await asyncio.to_thread(get_balance, user_id)
        return nuevo_saldo
