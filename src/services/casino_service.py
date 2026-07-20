import asyncio
import time
from typing import Tuple
from src.db import add_balance, deduct_balance, registrar_transaccion, record_game_result

class CasinoCircuitBreakerError(Exception):
    """Excepción lanzada cuando un juego del casino está deshabilitado por el circuit breaker."""
    pass

# Cache variables en memoria para la economía del servidor
_total_balance_cache = None
_total_balance_cache_time = 0

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
    async def get_total_server_balance() -> int:
        """Obtiene el balance total de todos los usuarios cacheado por 5 minutos."""
        global _total_balance_cache, _total_balance_cache_time
        ahora = time.time()
        if _total_balance_cache is None or (ahora - _total_balance_cache_time) > 300:
            from src.db import get_total_server_balance_db
            _total_balance_cache = await asyncio.to_thread(get_total_server_balance_db)
            _total_balance_cache_time = ahora
        return _total_balance_cache

    @staticmethod
    async def check_game_circuit_breaker(game_key: str) -> Tuple[bool, str]:
        """Retorna (True, '') si el juego está disponible, (False, mensaje) si está bloqueado."""
        from src.db import check_game_circuit_breaker_db
        return await asyncio.to_thread(check_game_circuit_breaker_db, game_key)

    @staticmethod
    async def place_bet(user_id: int, amount: int, game_type: str) -> Tuple[bool, int]:
        """Realiza la deducción del saldo para una apuesta de casino."""
        # Verificar el circuit breaker antes de proceder
        is_available, _ = await CasinoService.check_game_circuit_breaker(game_type)
        if not is_available:
            raise CasinoCircuitBreakerError("🚨 Este juego está temporalmente deshabilitado por mantenimiento de seguridad. Vuelve a intentarlo más tarde.")

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
        
        # --- CIRCUIT BREAKER POR JUEGO ---
        if profit > 0:
            from src.db import track_game_payout_db, activar_circuit_breaker_db
            total_pagado = await asyncio.to_thread(track_game_payout_db, game_type, profit)
            total_economia = await CasinoService.get_total_server_balance()
            
            if total_economia > 0 and total_pagado >= total_economia * 0.25:
                motivo = f"Pagó {total_pagado:,} (>25% de la economía total de {total_economia:,}) en un día"
                await asyncio.to_thread(activar_circuit_breaker_db, game_type, 2, motivo)
                
                # Notificación a staff en segundo plano
                asyncio.create_task(
                    CasinoService._notify_staff_circuit_breaker(game_type, total_pagado, total_economia, motivo)
                )

        return nuevo_saldo, impuesto

    @staticmethod
    async def _notify_staff_circuit_breaker(game_key: str, total_pagado: int, total_economia: int, motivo: str):
        """Envía una alerta detallada al canal de logs del staff."""
        import logging
        import discord
        from datetime import datetime
        logger = logging.getLogger("discord_bot")
        logger.warning(f"🚨 [CIRCUIT BREAKER] {game_key} activado. Payout: {total_pagado}, Economía: {total_economia}. Motivo: {motivo}")
        
        try:
            from src.bot import bot
            if not bot.is_ready():
                logger.info("[CIRCUIT BREAKER] El bot no está conectado/ready. Saltando notificación de Discord.")
                return
            logs_channel = bot.get_channel(1519413696206737559)
            if not logs_channel:
                logs_channel = await bot.fetch_channel(1519413696206737559)
                
            if logs_channel:
                embed = discord.Embed(
                    title="🚨 CIRCUIT BREAKER ACTIVADO",
                    description=f"El juego **{game_key}** ha sido deshabilitado automáticamente por 2 horas.",
                    color=discord.Color.dark_red(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="Juego", value=game_key, inline=True)
                embed.add_field(name="Monto Acumulado Hoy", value=f"{total_pagado:,} monedas", inline=True)
                embed.add_field(name="Economía Total Server", value=f"{total_economia:,} monedas", inline=True)
                pct = (total_pagado / total_economia) * 100 if total_economia > 0 else 0
                embed.add_field(name="% de la Economía", value=f"{pct:.2f}%", inline=True)
                embed.add_field(name="Motivo", value=motivo, inline=False)
                
                await logs_channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Error al enviar notificación de circuit breaker a Discord: {e}")

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

    @staticmethod
    async def get_user_streak_and_profit(user_id: int) -> dict:
        """Obtiene las estadísticas secretas de ganancias y rachas para balanceo en crash."""
        from src.db import db_cursor
        
        def _get_stats():
            stats = {"hot_streak": 0, "net_profit": 0}
            try:
                with db_cursor() as cursor:
                    cursor.execute("""
                        SELECT HotStreak, (TotalAmountWon - TotalAmountBet) 
                        FROM UserGameStats 
                        WHERE UserID = %s
                    """, (user_id,))
                    row = cursor.fetchone()
                    if row:
                        stats["hot_streak"] = max(0, row[0] if row[0] is not None else 0)
                        stats["net_profit"] = max(0, row[1] if row[1] is not None else 0)
            except Exception as e:
                import logging
                logging.getLogger("discord_bot").warning(f"Error al obtener estadísticas secretas en casino_service: {e}")
            return stats
            
        return await asyncio.to_thread(_get_stats)
