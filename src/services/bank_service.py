"""
bank_service.py — Lógica de negocio del Banco Central.

Gestiona préstamos (solicitar, pagar) sobre el pool de Reservas del banco.
Las funciones DB de bajo nivel viven en src/db.py.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Tuple

from src.db import (
    db_cursor,
    get_balance,
    add_balance,
    deduct_balance,
    get_bank_reserves,
    add_to_bank_reserves,
    get_user_loan,
)

logger = logging.getLogger(__name__)


def _request_loan_db(user_id: int, amount: int) -> Tuple[bool, str]:
    """Operación de DB para solicitar un préstamo. Bloqueante; llamar con asyncio.to_thread."""
    from src.db import get_user_prestige_level
    prestige_level = get_user_prestige_level(user_id)
    
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT LoanSlot, MontoAdeudado, LimitePrestamo, EnMora
            FROM UserLoans WHERE UserID = %s
        """, (user_id,))
        rows = cursor.fetchall()
        
        loans = {row[0]: {'MontoAdeudado': row[1], 'LimitePrestamo': row[2], 'EnMora': row[3]} for row in rows}
        
        any_in_mora = any(loan['EnMora'] for loan in loans.values())
        if any_in_mora:
            return False, "❌ Estás en **mora** en alguno de tus préstamos. Debes pagar tu deuda pendiente antes de solicitar un nuevo préstamo."

        target_slot = 1
        limite = 200000
        
        if prestige_level >= 2:
            if not loans:
                limite = 500000
            else:
                limite = max(loan['LimitePrestamo'] for loan in loans.values())
            
            slot1_ocupado = 1 in loans and loans[1]['MontoAdeudado'] > 0
            if slot1_ocupado:
                slot2_ocupado = 2 in loans and loans[2]['MontoAdeudado'] > 0
                if slot2_ocupado:
                    return False, "❌ Ya tienes dos préstamos activos (Slot 1 y Slot 2). Debes pagar al menos uno para pedir otro."
                target_slot = 2
        else:
            slot1_ocupado = 1 in loans and loans[1]['MontoAdeudado'] > 0
            if slot1_ocupado:
                return False, f"❌ Ya tienes un préstamo activo de **{loans[1]['MontoAdeudado']:,}** monedas. Págalo antes de pedir otro."
            if 1 in loans:
                limite = loans[1]['LimitePrestamo']

        if amount <= 0:
            return False, "❌ El monto del préstamo debe ser mayor a 0."

        if amount > limite:
            return False, (
                f"❌ El monto solicitado ({amount:,}) supera tu límite de préstamo actual "
                f"(**{limite:,}** monedas).\n"
                f"💡 Paga tus préstamos a tiempo para aumentar tu límite."
            )

        cursor.execute("SELECT Reservas FROM BancoCentral WHERE ID = 1")
        banco_row = cursor.fetchone()
        reservas = banco_row[0] if banco_row else 0

        if amount > reservas:
            return False, (
                f"❌ El Banco Central no tiene suficientes reservas para ese préstamo.\n"
                f"💰 Reservas disponibles: **{reservas:,}** monedas."
            )

        ahora = datetime.now()
        vencimiento = ahora + timedelta(days=7)

        cursor.execute("""
            INSERT INTO Users (UserID, Balance) VALUES (%s, %s)
            ON CONFLICT (UserID) DO UPDATE SET Balance = Users.Balance + EXCLUDED.Balance
        """, (user_id, amount))

        cursor.execute(
            "UPDATE BancoCentral SET Reservas = Reservas - %s WHERE ID = 1",
            (amount,)
        )

        cursor.execute("""
            INSERT INTO UserLoans (UserID, LoanSlot, MontoAdeudado, FechaPrestamo, FechaVencimiento, LimitePrestamo)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (UserID, LoanSlot) DO UPDATE
                SET MontoAdeudado = %s,
                    FechaPrestamo = %s,
                    FechaVencimiento = %s,
                    EnMora = FALSE
        """, (
            user_id, target_slot, amount, ahora, vencimiento, limite,
            amount, ahora, vencimiento
        ))

        slot_text = f" (Slot {target_slot})" if prestige_level >= 2 else ""
        return True, (
            f"✅ ¡Préstamo aprobado{slot_text}!\n"
            f"💵 **Monto:** {amount:,} monedas acreditadas a tu cuenta.\n"
            f"📅 **Vencimiento:** {vencimiento.strftime('%d/%m/%Y')}\n"
            f"⚠️ Si no pagas antes del vencimiento entrarás en **mora** "
            f"y se retendrá un 10% de tus ingresos de trabajo."
        )


def _repay_loan_db(user_id: int, amount: int, slot: int = 1) -> Tuple[bool, str]:
    """Operación de DB para pagar (parcial o total) un préstamo. Bloqueante."""
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT MontoAdeudado, FechaVencimiento, LimitePrestamo,
                   PrestamosPagadosATiempo, EnMora
            FROM UserLoans WHERE UserID = %s AND LoanSlot = %s
        """, (user_id, slot))
        row = cursor.fetchone()

        if not row or row[0] <= 0:
            return False, f"❌ No tienes ningún préstamo activo que pagar en el **Slot {slot}**."

        monto_adeudado, vencimiento, limite, pagados_a_tiempo, en_mora = row

        if amount <= 0:
            return False, "❌ El monto a pagar debe ser mayor a 0."

        pago_real = min(amount, monto_adeudado)

        cursor.execute("SELECT Balance FROM Users WHERE UserID = %s", (user_id,))
        balance_row = cursor.fetchone()
        balance = balance_row[0] if balance_row else 0

        if balance < pago_real:
            return False, (
                f"❌ No tienes suficiente saldo.\n"
                f"💸 Necesitas: **{pago_real:,}** | Tienes: **{balance:,}** monedas."
            )

        cursor.execute("""
            UPDATE Users SET Balance = Balance - %s
            WHERE UserID = %s AND Balance >= %s
            RETURNING Balance
        """, (pago_real, user_id, pago_real))
        if not cursor.fetchone():
            return False, "❌ Error de concurrencia al descontar el saldo. Inténtalo de nuevo."

        nuevo_monto = monto_adeudado - pago_real

        cursor.execute(
            "UPDATE BancoCentral SET Reservas = Reservas + %s WHERE ID = 1",
            (pago_real,)
        )

        ahora = datetime.now()

        if nuevo_monto <= 0:
            nuevo_limite = limite
            nuevos_pagados = pagados_a_tiempo
            bono_msg = ""

            if vencimiento and ahora <= vencimiento:
                nuevos_pagados += 1
                nuevo_limite = int(limite * 1.20)
                bono_msg = (
                    f"\n🎉 ¡Pagaste a tiempo! Tu límite de préstamo ha subido a "
                    f"**{nuevo_limite:,}** monedas."
                )

            cursor.execute("""
                UPDATE UserLoans SET
                    MontoAdeudado = 0,
                    FechaPrestamo = NULL,
                    FechaVencimiento = NULL,
                    LimitePrestamo = %s,
                    PrestamosPagadosATiempo = %s,
                    EnMora = FALSE
                WHERE UserID = %s AND LoanSlot = %s
            """, (nuevo_limite, nuevos_pagados, user_id, slot))

            cursor.execute("""
                UPDATE UserLoans SET LimitePrestamo = %s WHERE UserID = %s
            """, (nuevo_limite, user_id))

            return True, (
                f"✅ **¡Préstamo saldado en Slot {slot}!** Pagaste **{pago_real:,}** monedas.{bono_msg}"
            )
        else:
            cursor.execute("""
                UPDATE UserLoans SET MontoAdeudado = %s WHERE UserID = %s AND LoanSlot = %s
            """, (nuevo_monto, user_id, slot))

            mora_txt = " ⚠️ *Sigues en mora.*" if en_mora else ""
            return True, (
                f"✅ Pagaste **{pago_real:,}** monedas en Slot {slot}.\n"
                f"💳 Deuda restante: **{nuevo_monto:,}** monedas.{mora_txt}"
            )


def _apply_daily_interest_db() -> dict:
    """Aplica interés diario (0.5%) a todos los préstamos activos y marca mora."""
    from datetime import datetime
    ahora = datetime.now()

    with db_cursor() as cursor:
        cursor.execute("""
            SELECT UserID, MontoAdeudado, FechaVencimiento, LoanSlot
            FROM UserLoans WHERE MontoAdeudado > 0
        """)
        prestamos = cursor.fetchall()

        total_interes = 0
        mora_nuevos = []

        for user_id, monto, venc, slot in prestamos:
            interes = max(1, int(monto * 0.005))
            nuevo_monto = monto + interes
            total_interes += interes

            en_mora_nueva = (venc is not None and ahora > venc)

            cursor.execute("""
                UPDATE UserLoans
                SET MontoAdeudado = %s,
                    EnMora = %s
                WHERE UserID = %s AND LoanSlot = %s
            """, (nuevo_monto, en_mora_nueva, user_id, slot))

            if en_mora_nueva:
                mora_nuevos.append(user_id)

        if total_interes > 0:
            cursor.execute(
                "UPDATE BancoCentral SET Reservas = Reservas + %s WHERE ID = 1",
                (total_interes,)
            )

    return {
        'prestamos_procesados': len(prestamos),
        'total_interes': total_interes,
        'en_mora': mora_nuevos,
    }


class BankService:
    """Servicio del Banco Central — métodos async para usar desde comandos y tareas."""

    @staticmethod
    async def request_loan(user_id: int, amount: int) -> Tuple[bool, str]:
        """Solicita un préstamo. Retorna (éxito, mensaje)."""
        return await asyncio.to_thread(_request_loan_db, user_id, amount)

    @staticmethod
    async def repay_loan(user_id: int, amount: int, slot: int = 1) -> Tuple[bool, str]:
        """Paga (parcial o total) un préstamo. Retorna (éxito, mensaje)."""
        return await asyncio.to_thread(_repay_loan_db, user_id, amount, slot)

    @staticmethod
    async def apply_daily_interest() -> dict:
        """Aplica interés diario y marca mora. Retorna resumen de la operación."""
        return await asyncio.to_thread(_apply_daily_interest_db)

    @staticmethod
    async def get_reserves() -> int:
        """Retorna las reservas actuales del banco."""
        return await asyncio.to_thread(get_bank_reserves)

    @staticmethod
    async def get_user_loan(user_id: int, slot: int = 1) -> dict | None:
        """Retorna el préstamo activo del usuario, o None si no tiene."""
        return await asyncio.to_thread(get_user_loan, user_id, slot)

    @staticmethod
    async def get_all_loans(user_id: int) -> list:
        """Retorna todos los préstamos del usuario."""
        from src.db import get_all_user_loans
        return await asyncio.to_thread(get_all_user_loans, user_id)

    @staticmethod
    async def start_investment(user_id: int, amount: int):
        """Inicia una inversión. Retorna un objeto InvestmentStartResult."""
        from src.db import start_investment_db, InvestmentStartResult
        return await asyncio.to_thread(start_investment_db, user_id, amount)

    @staticmethod
    async def resolve_matured_investments() -> dict:
        """Resuelve inversiones vencidas. Retorna resumen."""
        from src.db import resolve_matured_investments_db
        return await asyncio.to_thread(resolve_matured_investments_db)

    @staticmethod
    async def get_active_investment(user_id: int) -> dict | None:
        """Obtiene la inversión activa del usuario, o None si no tiene."""
        from src.db import get_active_investment_db
        return await asyncio.to_thread(get_active_investment_db, user_id)

    @staticmethod
    async def get_bank_balance(user_id: int) -> int:
        """Obtiene el saldo bancario actual de un usuario."""
        from src.db import get_bank_balance
        return await asyncio.to_thread(get_bank_balance, user_id)

    @staticmethod
    async def deposit_to_bank(user_id: int, amount: int) -> Tuple[bool, str, int, int]:
        """Realiza el depósito de dinero al banco."""
        from src.db import deposit_to_bank_db
        return await asyncio.to_thread(deposit_to_bank_db, user_id, amount)

    @staticmethod
    async def withdraw_from_bank(user_id: int, amount: int) -> Tuple[bool, str, int, int]:
        """Realiza el retiro de dinero del banco."""
        from src.db import withdraw_from_bank_db
        return await asyncio.to_thread(withdraw_from_bank_db, user_id, amount)

    @staticmethod
    async def apply_daily_bank_fee() -> list:
        """Cobra la comisión diaria del 1% por custodia a todos los usuarios."""
        from src.db import apply_daily_bank_fee_db
        return await asyncio.to_thread(apply_daily_bank_fee_db)




