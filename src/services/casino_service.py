import asyncio
from typing import Tuple
from src.db import add_balance, deduct_balance, registrar_transaccion, record_game_result

class CasinoService:
    @staticmethod
    async def check_casino_lockout(user_id: int) -> Tuple[bool, str]:
        """Retorna (True, '') si puede jugar, (False, mensaje) si está bloqueado."""
        from src.db import get_casino_lockout_data, update_casino_reference_balance
        from datetime import datetime
        
        balance, saldo_ref, ts_ref, bloqueado_hasta = await asyncio.to_thread(get_casino_lockout_data, user_id)
        
        ahora = datetime.now()
        if bloqueado_hasta and bloqueado_hasta > ahora:
            restante = bloqueado_hasta - ahora
            minutos = int(restante.total_seconds() // 60)
            segundos = int(restante.total_seconds() % 60)
            tiempo_str = f"{minutos}m {segundos}s" if minutos > 0 else f"{segundos}s"
            return False, f"🎰 Estás bloqueado del casino temporalmente. Por favor, tómate un descanso. Tiempo restante: `{tiempo_str}`."
            
        if saldo_ref is None or ts_ref is None or (ahora - ts_ref).total_seconds() > 86400:
            await asyncio.to_thread(update_casino_reference_balance, user_id, balance, ahora)
            
        return True, ""

    @staticmethod
    async def check_and_apply_winstreak_lockout(user_id: int, nuevo_balance: int) -> bool:
        """Retorna True si se activó el bloqueo en este momento (para poder avisarle al jugador)."""
        from src.db import get_casino_lockout_data, apply_casino_lockout
        from datetime import datetime, timedelta
        
        _, saldo_ref, _, _ = await asyncio.to_thread(get_casino_lockout_data, user_id)
        
        if saldo_ref is None:
            from src.db import update_casino_reference_balance
            await asyncio.to_thread(update_casino_reference_balance, user_id, nuevo_balance, datetime.now())
            return False
            
        ref_val = max(1, saldo_ref)
        
        if (nuevo_balance - saldo_ref) >= (ref_val * 0.25):
            bloqueado_hasta = datetime.now() + timedelta(minutes=25)
            await asyncio.to_thread(apply_casino_lockout, user_id, bloqueado_hasta, nuevo_balance)
            return True
            
        return False

    @staticmethod
    async def place_bet(user_id: int, amount: int, game_type: str) -> Tuple[bool, int]:
        """Realiza la deducción del saldo para una apuesta de casino."""
        success, new_balance = await asyncio.to_thread(deduct_balance, user_id, amount)
        if success:
            await asyncio.to_thread(registrar_transaccion, user_id, -amount, f"Apuesta en {game_type}")
        return success, new_balance

    @staticmethod
    async def settle_win(user_id: int, bet_amount: int, winnings: int, game_type: str, difficulty_modifier: float, current_balance: int) -> Tuple[int, int]:
        """Procesa una victoria en el casino: acredita el premio y registra estadísticas."""
        from src.utils.economy_config import TRANSACTION_TAX
        impuesto = int(winnings * TRANSACTION_TAX["casino"])
        winnings_netos = winnings - impuesto
        profit = winnings_netos - bet_amount
        # Winnings es el dinero retornado total (incluye apuesta). Si el juego es 1:1, winnings = bet * 2, profit = bet.
        await asyncio.to_thread(add_balance, user_id, winnings_netos)
        nuevo_saldo = current_balance + winnings_netos
        
        await asyncio.to_thread(registrar_transaccion, user_id, profit, f"{game_type.capitalize()}: Ganó partida")
        await asyncio.to_thread(record_game_result, user_id, game_type, bet_amount, 'win', profit, difficulty_modifier, nuevo_saldo)
        return nuevo_saldo, impuesto

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
