import asyncio
import random
import logging
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, List
from src.db import (
    get_user_ticket_count,
    comprar_boleto_db,
    get_lottery_state,
    get_active_tickets,
    process_lottery_draw_db
)

logger = logging.getLogger(__name__)

class LotteryService:
    TICKET_COST = 500
    MAX_TICKETS_PER_DAY = 5
    POOL_FLOOR = 10000

    @staticmethod
    async def get_state() -> Dict[str, Any]:
        """Obtiene el estado actual de la lotería (pozo y próximas fechas)."""
        return await asyncio.to_thread(get_lottery_state)

    @staticmethod
    async def get_user_tickets(user_id: int) -> int:
        """Obtiene el número de boletos comprados por el usuario para el sorteo actual."""
        return await asyncio.to_thread(get_user_ticket_count, user_id)

    @staticmethod
    async def purchase_ticket(user_id: int, numbers: List[int]) -> Tuple[bool, str, int]:
        """
        Intenta comprar un boleto de lotería para el usuario.
        
        Args:
            user_id: ID de Discord del usuario.
            numbers: Lista de 4 enteros elegidos.
            
        Returns:
            Tuple[bool, str, int]: (Éxito, Mensaje de respuesta, Nuevo saldo si tuvo éxito)
        """
        # 1. Validar cantidad de números
        if len(numbers) != 4:
            return False, "Debes seleccionar exactamente 4 números.", 0

        # 2. Validar rango
        for num in numbers:
            if num < 1 or num > 25:
                return False, "Cada número debe estar entre 1 y 25 (inclusive).", 0

        # 3. Validar duplicados
        if len(set(numbers)) != 4:
            return False, "Los números seleccionados no se pueden repetir.", 0

        # 4. Validar límite de boletos diario
        current_count = await asyncio.to_thread(get_user_ticket_count, user_id)
        if current_count >= LotteryService.MAX_TICKETS_PER_DAY:
            return False, f"Ya has alcanzado el límite de {LotteryService.MAX_TICKETS_PER_DAY} boletos de loto para hoy.", 0

        # 5. Formatear y ordenar números
        sorted_numbers = sorted(numbers)
        numbers_str = ",".join(map(str, sorted_numbers))

        # 6. Ejecutar en base de datos de forma atómica
        success, new_balance = await asyncio.to_thread(
            comprar_boleto_db, user_id, numbers_str, LotteryService.TICKET_COST
        )
        
        if not success:
            return False, f"No tienes suficiente saldo. Cada boleto cuesta {LotteryService.TICKET_COST} monedas.", 0

        num_display = ", ".join(map(str, sorted_numbers))
        return True, f"✅ ¡Boleto comprado con éxito! Números: `[{num_display}]`", new_balance

    @staticmethod
    async def draw_lottery() -> Dict[str, Any]:
        """
        Realiza el sorteo diario de la lotería.
        
        Returns:
            Dict[str, Any]: Diccionario con los números ganadores, ganadores por categoría,
                            pozo anterior, nuevo pozo, etc.
        """
        # 1. Obtener estado actual y boletos comprados
        state = await asyncio.to_thread(get_lottery_state)
        current_pool = state['pool']
        
        tickets = await asyncio.to_thread(get_active_tickets)
        
        # Calcular fecha del último y próximo sorteo
        last_draw = datetime.now()
        next_draw = last_draw + timedelta(days=1)
        # Siguiente sorteo a las 00:00:00 del día siguiente
        next_draw = next_draw.replace(hour=0, minute=0, second=0, microsecond=0)

        # Si no hay boletos, no hay sorteo necesario. Solo actualizar fechas
        if not tickets:
            logger.info("Sorteo de lotería ejecutado sin boletos activos.")
            await asyncio.to_thread(process_lottery_draw_db, [], current_pool, last_draw, next_draw)
            return {
                'winning_numbers': [],
                'pool': current_pool,
                'new_pool': current_pool,
                'winners_4': [],
                'winners_3': [],
                'winners_2': [],
                'winners_1': [],
                'total_tickets': 0,
                'no_tickets': True,
                'participants': []
            }

        # 2. Generar números ganadores (4 números únicos del 1 al 25)
        winning_numbers = sorted(random.sample(range(1, 26), 4))
        winning_set = set(winning_numbers)
        logger.info(f"Sorteo de lotería iniciado. Números ganadores: {winning_numbers}")

        # 3. Clasificar ganadores
        winners_4 = []
        winners_3 = []
        winners_2 = []
        winners_1 = []

        for user_id, numbers_str in tickets:
            try:
                ticket_numbers = set(map(int, numbers_str.split(",")))
                matches = len(winning_set.intersection(ticket_numbers))
                if matches == 4:
                    winners_4.append(user_id)
                elif matches == 3:
                    winners_3.append(user_id)
                elif matches == 2:
                    winners_2.append(user_id)
                elif matches == 1:
                    winners_1.append(user_id)
            except Exception as e:
                logger.error(f"Error procesando boleto de usuario {user_id}: {e}")

        # 4. Calcular premios compartidos e individuales
        payouts = {} # user_id -> (payout, matches)

        # 4 Aciertos: 100% del pozo compartido
        if winners_4:
            share_4 = current_pool // len(winners_4)
            for uid in winners_4:
                payouts[uid] = payouts.get(uid, 0) + share_4

        # 3 Aciertos: 15% del pozo compartido
        if winners_3:
            share_3 = int(current_pool * 0.15) // len(winners_3)
            for uid in winners_3:
                payouts[uid] = payouts.get(uid, 0) + share_3

        # 2 Aciertos: 2% del pozo compartido
        if winners_2:
            share_2 = int(current_pool * 0.02) // len(winners_2)
            for uid in winners_2:
                payouts[uid] = payouts.get(uid, 0) + share_2

        # 1 Acierto: 200 monedas fijas cada uno
        if winners_1:
            for uid in winners_1:
                payouts[uid] = payouts.get(uid, 0) + 200

        # Formatear datos para la base de datos
        winners_data = []
        total_payout_amount = 0
        for uid, amount in payouts.items():
            matches = 0
            if uid in winners_4: matches = 4
            elif uid in winners_3: matches = 3
            elif uid in winners_2: matches = 2
            elif uid in winners_1: matches = 1
            
            winners_data.append((uid, amount, matches))
            total_payout_amount += amount

        # 5. Calcular nuevo pozo tras el sorteo
        if winners_4:
            # Si alguien gana el jackpot, el pozo se reinicia al piso
            new_pool = LotteryService.POOL_FLOOR
        else:
            # Si nadie gana el jackpot, restamos los premios menores y acumulamos el resto
            new_pool = current_pool - total_payout_amount
            if new_pool < LotteryService.POOL_FLOOR:
                new_pool = LotteryService.POOL_FLOOR

        # 6. Registrar en DB de forma atómica
        await asyncio.to_thread(
            process_lottery_draw_db, winners_data, new_pool, last_draw, next_draw
        )

        participants = list(set(user_id for user_id, _ in tickets))
        return {
            'winning_numbers': winning_numbers,
            'pool': current_pool,
            'new_pool': new_pool,
            'winners_4': winners_4,
            'winners_3': winners_3,
            'winners_2': winners_2,
            'winners_1': winners_1,
            'total_tickets': len(tickets),
            'no_tickets': False,
            'payouts': payouts,
            'participants': participants
        }
