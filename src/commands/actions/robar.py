import discord
from discord.ext import commands
import discord.app_commands as app_commands
import logging
import typing

logger = logging.getLogger(__name__)
import random
import asyncio
from datetime import datetime, timedelta
from src.db import ensure_user, db_cursor
from src.utils.dynamic_difficulty import DynamicDifficulty
from src.utils.robo_progression import (
    get_thief_bonuses,
    get_cooldown_minutes,
    calc_xp_from_robbery,
    apply_thief_xp,
    remove_thief_xp,
    get_rank_name,
    format_progress_bar,
    calc_xp_needed,
    get_protection_minutes,
    calcular_robo_dinamico,
    get_bad_luck_bonus,
    THIEF_MILESTONES,
    ROBO_COOLDOWN_MINUTES,
)
from src.utils.cooldowns import ECONOMY_COOLDOWN

# Factor de reducción de cooldown cuando el robo falla (60% del cooldown normal)
FAIL_COOLDOWN_FACTOR = 0.6
VICTIMA_MIN_SALDO = 1000

def _get_thief_stats(cursor, user_id, for_update=False):
    lock = " FOR UPDATE" if for_update else ""
    cursor.execute(f"""
        SELECT COALESCE(ThiefLevel, 1), COALESCE(ThiefXP, 0),
               LastRoboTime, COALESCE(RobosExitosos, 0),
               COALESCE(RobosFallidosConsecutivos, 0)
        FROM RoboStats WHERE UserID = %s{lock}
    """, (user_id,))
    row = cursor.fetchone()
    if not row:
        return 1, 0, None, 0, 0
    return row[0], row[1], row[2], row[3], row[4]

def _format_timedelta(td: timedelta, show_seconds: bool = False) -> str:
    total_segundos = max(0, int(td.total_seconds()))
    horas, resto = divmod(total_segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    
    partes = []
    if horas > 0:
        partes.append(f"{horas}h")
    if minutos > 0 or (not horas and not show_seconds):
        partes.append(f"{minutos}m")
    if show_seconds and (segundos > 0 or not partes):
        partes.append(f"{segundos}s")
        
    return " ".join(partes) if partes else ("0s" if show_seconds else "0m")

def _ejecutar_robo_db(ladron_id, victima_id, ladron_name, victima_name):
    """
    Realiza todas las validaciones de negocio y transacciones de base de datos para el robo de forma atómica en PostgreSQL.
    El porcentaje de robo se calcula DINÁMICAMENTE basándose en la diferencia de riqueza.
    Retorna una tupla (status, data)
    - status: 'cooldown' | 'protection' | 'no_money' | 'success' | 'fail'
    """
    # Asegurar que ambos usuarios existan en la base de datos
    ensure_user(ladron_id, ladron_name)
    ensure_user(victima_id, victima_name)
    
    with db_cursor() as cursor:
        # Obtener una marca de tiempo consistente desde la base de datos para todo el flujo
        cursor.execute("SELECT NOW()")
        ahora_db = cursor.fetchone()[0]
        if ahora_db and ahora_db.tzinfo is not None:
            ahora_db = ahora_db.replace(tzinfo=None)

        # Inicializar registros de robo si no existen usando ON CONFLICT
        cursor.execute("INSERT INTO RoboStats (UserID) VALUES (%s) ON CONFLICT (UserID) DO NOTHING", (ladron_id,))
        cursor.execute("INSERT INTO RoboStats (UserID) VALUES (%s) ON CONFLICT (UserID) DO NOTHING", (victima_id,))

        thief_level, thief_xp, last_robo, robos_exitosos, fallos_consecutivos = _get_thief_stats(cursor, ladron_id, for_update=True)
        if last_robo and last_robo.tzinfo is not None:
            last_robo = last_robo.replace(tzinfo=None)
        cooldown_minutes = get_cooldown_minutes(thief_level)
        
        # Verificar cooldown de robo (reducido por nivel)
        if last_robo and ahora_db - last_robo < timedelta(minutes=cooldown_minutes):
            tiempo_restante = last_robo + timedelta(minutes=cooldown_minutes) - ahora_db
            return 'cooldown', {'tiempo_restante': tiempo_restante, 'cooldown_minutes': cooldown_minutes}
        
        # Obtener saldos bloqueando las filas (evita condiciones de carrera)
        id_1, id_2 = min(ladron_id, victima_id), max(ladron_id, victima_id)
        user_ids = [id_1, id_2]
        cursor.execute("SELECT UserID, Balance FROM Users WHERE UserID = ANY(%s) FOR UPDATE", (user_ids,))
        rows = cursor.fetchall()
        if len(rows) != 2:
            raise ValueError("No se pudieron obtener los saldos de ambos usuarios (fila faltante en base de datos).")
        
        saldo_ladron = 0
        saldo_victima = 0
        for uid, bal in rows:
            if uid == ladron_id:
                saldo_ladron = bal
            elif uid == victima_id:
                saldo_victima = bal
        
        # Verificar si la víctima tiene saldo suficiente (al menos VICTIMA_MIN_SALDO)
        if saldo_victima < VICTIMA_MIN_SALDO:
            return 'no_money', {}
        
        # Verificar si la víctima tiene un Escudo Total activo
        cursor.execute("SELECT ShieldExpiry FROM RoboStats WHERE UserID = %s", (victima_id,))
        res_shield = cursor.fetchone()
        shield_expiry = res_shield[0] if res_shield else None
        if shield_expiry and shield_expiry.tzinfo is not None:
            shield_expiry = shield_expiry.replace(tzinfo=None)
            
        if shield_expiry and ahora_db < shield_expiry:
            tiempo_restante = shield_expiry - ahora_db
            return 'shield_active', {'tiempo_restante': tiempo_restante}

        # Verificar protección de la víctima (según Cuota de Protección)
        protection_minutes = get_protection_minutes(victima_id)
        cursor.execute("SELECT LastRobadoTime FROM RoboStats WHERE UserID = %s", (victima_id,))
        result = cursor.fetchone()
        last_robado = result[0] if result else None
        if last_robado and last_robado.tzinfo is not None:
            last_robado = last_robado.replace(tzinfo=None)
        
        if last_robado and ahora_db - last_robado < timedelta(minutes=protection_minutes):
            tiempo_restante = last_robado + timedelta(minutes=protection_minutes) - ahora_db
            return 'protection', {'tiempo_restante': tiempo_restante, 'protection_minutes': protection_minutes}
        
        # ============================================================
        # CÁLCULO DINÁMICO DEL ROBO
        # ============================================================
        robo_params = calcular_robo_dinamico(saldo_ladron, saldo_victima, thief_level)
        porcentaje = robo_params["porcentaje_robo"]
        prob_exito = robo_params["prob_exito"]
        penalizacion_pct = robo_params["penalizacion_pct"]
        
        # Calcular cantidad a robar
        cantidad_a_robar = int(saldo_victima * (porcentaje / 100))
        cantidad_a_robar = max(1, cantidad_a_robar)
        
        # Aplicar bonus por robos exitosos (experiencia en el campo)
        if robos_exitosos > 20:
            prob_exito += 5
        elif robos_exitosos > 10:
            prob_exito += 3
        elif robos_exitosos > 5:
            prob_exito += 1
        
        # Aplicar bonus por racha de mala suerte
        bad_luck = get_bad_luck_bonus(fallos_consecutivos)
        prob_exito += bad_luck["prob_bonus"]
        
        # Aplicar dificultad dinámica (reducida para robos: ×15 en vez de ×30)
        difficulty_modifier, _ = DynamicDifficulty.calculate_dynamic_difficulty(
            ladron_id, cantidad_a_robar, 'robo'
        )
        prob_exito -= int(difficulty_modifier * 15)
        prob_exito = max(10, min(90, prob_exito))
        
        # Registrar intento de robo (actualizar cooldown)
        cursor.execute("UPDATE RoboStats SET LastRoboTime = CURRENT_TIMESTAMP WHERE UserID = %s", (ladron_id,))
        
        # Determinar resultado del robo
        exito = random.randint(1, 100) <= int(prob_exito)
        
        thief_bonuses = get_thief_bonuses(thief_level)
        
        if exito:
            bonus_loot = int(cantidad_a_robar * thief_bonuses["loot_bonus_pct"])
            cantidad_total = cantidad_a_robar + bonus_loot

            cursor.execute("UPDATE Users SET Balance = Balance - %s WHERE UserID = %s RETURNING Balance", (cantidad_a_robar, victima_id))
            nuevo_saldo_victima = cursor.fetchone()[0]
            
            cursor.execute("UPDATE Users SET Balance = Balance + %s WHERE UserID = %s RETURNING Balance", (cantidad_total, ladron_id))
            nuevo_saldo_ladron = cursor.fetchone()[0]
            
            cursor.execute("""
                INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            """, (ladron_id, cantidad_total, f"Robo: éxito vs {victima_name}"))
            cursor.execute("""
                INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            """, (victima_id, -cantidad_a_robar, f"Robado por {ladron_name}"))
            
            xp_ganada = calc_xp_from_robbery(cantidad_a_robar)
            xp_result = apply_thief_xp(thief_level, thief_xp, xp_ganada)

            cursor.execute("""
                UPDATE RoboStats SET 
                RobosExitosos = COALESCE(RobosExitosos, 0) + 1,
                RobosFallidosConsecutivos = 0,
                TotalRobado = COALESCE(TotalRobado, 0) + %s,
                ThiefLevel = %s,
                ThiefXP = %s
                WHERE UserID = %s
            """, (cantidad_a_robar, xp_result["level"], xp_result["xp"], ladron_id))
            
            cursor.execute("""
                UPDATE RoboStats SET 
                TotalPerdido = COALESCE(TotalPerdido, 0) + %s,
                LastRobadoTime = CURRENT_TIMESTAMP
                WHERE UserID = %s
            """, (cantidad_a_robar, victima_id))
            
            # Registrar en log
            cursor.execute("""
                INSERT INTO RoboLog (LadronID, VictimaID, CantidadRobada, Exitoso)
                VALUES (%s, %s, %s, TRUE)
            """, (ladron_id, victima_id, cantidad_a_robar))
            
            return 'success', {
                'cantidad_a_robar': cantidad_a_robar,
                'bonus_loot': bonus_loot,
                'cantidad_total': cantidad_total,
                'nuevo_saldo_ladron': nuevo_saldo_ladron,
                'nuevo_saldo_victima': nuevo_saldo_victima,
                'xp_ganada': xp_ganada,
                'thief_level': xp_result["level"],
                'thief_xp': xp_result["xp"],
                'xp_for_next': xp_result["xp_for_next"],
                'leveled_up': xp_result["leveled_up"],
                'previous_level': xp_result["previous_level"],
                'rank': xp_result["rank"],
                'cooldown_minutes': get_cooldown_minutes(xp_result["level"]),
                'protection_minutes': protection_minutes,
                'robo_params': robo_params,
                'prob_exito_final': int(prob_exito),
            }
        else:
            # Penalización dinámica basada en el tier (nota: penalizacion_pct ya incorpora
            # la reducción de multa por nivel de ladrón calculada en calcular_robo_dinamico)
            penalizacion = int(cantidad_a_robar * (penalizacion_pct / 100))
            # Aplicar reducción por racha de mala suerte
            penalizacion = int(penalizacion * bad_luck["penalty_mult"])
            penalizacion = min(penalizacion, saldo_ladron)
            
            nuevo_saldo_ladron = saldo_ladron - penalizacion
            if penalizacion > 0:
                cursor.execute("UPDATE Users SET Balance = %s WHERE UserID = %s", (nuevo_saldo_ladron, ladron_id))
                cursor.execute("""
                    INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                """, (ladron_id, -penalizacion, "Multa por intento de robo"))
            
            # Actualizar estadísticas de robo fallido
            xp_perdida = calc_xp_from_robbery(cantidad_a_robar)
            xp_result = remove_thief_xp(thief_level, thief_xp, xp_perdida)

            # Cooldown reducido al fallar: retroceder el LastRoboTime para acortar la espera
            cooldown_actual = get_cooldown_minutes(xp_result["level"])
            reduccion_secs = int(cooldown_actual * 60 * (1 - FAIL_COOLDOWN_FACTOR))
            cursor.execute("""
                UPDATE RoboStats SET 
                RobosFallidos = COALESCE(RobosFallidos, 0) + 1,
                RobosFallidosConsecutivos = COALESCE(RobosFallidosConsecutivos, 0) + 1,
                TotalPerdido = COALESCE(TotalPerdido, 0) + %s,
                ThiefLevel = %s,
                ThiefXP = %s,
                LastRoboTime = CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                WHERE UserID = %s
            """, (penalizacion, xp_result["level"], xp_result["xp"], reduccion_secs, ladron_id))
            
            # Registrar en log
            cursor.execute("""
                INSERT INTO RoboLog (LadronID, VictimaID, CantidadRobada, Exitoso)
                VALUES (%s, %s, %s, FALSE)
            """, (ladron_id, victima_id, 0))
            
            cooldown_efectivo = int(cooldown_actual * FAIL_COOLDOWN_FACTOR)
            
            return 'fail', {
                'penalizacion': penalizacion,
                'nuevo_saldo_ladron': nuevo_saldo_ladron,
                'xp_perdida': xp_result["xp_lost"],
                'thief_level': xp_result["level"],
                'thief_xp': xp_result["xp"],
                'xp_for_next': xp_result["xp_for_next"],
                'leveled_down': xp_result["leveled_down"],
                'previous_level': xp_result["previous_level"],
                'rank': xp_result["rank"],
                'cooldown_minutes': cooldown_efectivo,
                'robo_params': robo_params,
                'prob_exito_final': int(prob_exito),
                'bad_luck_desc': bad_luck["descripcion"],
                'fallos_consecutivos': fallos_consecutivos + 1,
            }

class RoboBandaInvitationView(discord.ui.View):
    def __init__(self, initiator: discord.Member, accomplice: discord.Member, target, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.initiator = initiator
        self.accomplice = accomplice
        self.target = target
        self.accepted = None
        self.message = None  # DM message object to edit later if needed

    @discord.ui.button(label="Aceptar golpe", style=discord.ButtonStyle.green, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.accomplice.id:
            await interaction.response.send_message("❌ Esta invitación no es para ti.", ephemeral=True)
            return

        self.accepted = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="✅ Has aceptado la invitación.", view=self)
        self.stop()

    @discord.ui.button(label="Rechazar golpe", style=discord.ButtonStyle.red, emoji="❌")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.accomplice.id:
            await interaction.response.send_message("❌ Esta invitación no es para ti.", ephemeral=True)
            return

        self.accepted = False
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ Has rechazado la invitación.", view=self)
        self.stop()
        
        # Notify the initiator via DM
        try:
            target_str = "el Banco Central" if isinstance(self.target, str) else self.target.display_name
            await self.initiator.send(f"❌ {self.accomplice.display_name} ha rechazado tu invitación para robar a {target_str}.")
        except Exception:
            pass

    async def on_timeout(self):
        if self.accepted is None:
            self.accepted = False
            for child in self.children:
                child.disabled = True
            
            # Edit DM if possible
            if self.message:
                try:
                    await self.message.edit(content="⏰ La invitación ha expirado.", view=self)
                except Exception:
                    pass
            
            # Notify initiator via DM
            try:
                target_str = "el Banco Central" if isinstance(self.target, str) else self.target.display_name
                await self.initiator.send(f"⏰ La invitación a {self.accomplice.display_name} para robar a {target_str} ha expirado.")
            except Exception:
                pass

def _ejecutar_robo_banda_db(iniciador_id, complice_id, victima_id, iniciador_name, complice_name, victima_name):
    """
    Realiza la lógica de base de datos para un robo en banda contra un jugador.
    Garantiza atomicidad y bloquea las filas de los usuarios para evitar condiciones de carrera.
    """
    ensure_user(iniciador_id, iniciador_name)
    ensure_user(complice_id, complice_name)
    ensure_user(victima_id, victima_name)

    with db_cursor() as cursor:
        cursor.execute("SELECT NOW()")
        ahora_db = cursor.fetchone()[0]
        if ahora_db and ahora_db.tzinfo is not None:
            ahora_db = ahora_db.replace(tzinfo=None)

        # Inicializar estadísticas de robo si no existen
        cursor.execute("INSERT INTO RoboStats (UserID) VALUES (%s) ON CONFLICT (UserID) DO NOTHING", (iniciador_id,))
        cursor.execute("INSERT INTO RoboStats (UserID) VALUES (%s) ON CONFLICT (UserID) DO NOTHING", (complice_id,))
        cursor.execute("INSERT INTO RoboStats (UserID) VALUES (%s) ON CONFLICT (UserID) DO NOTHING", (victima_id,))

        # Bloquear y obtener estadísticas de robo
        # Ordenamos los IDs para evitar deadlocks y bloqueamos todas las filas en una sola consulta
        ids_stats = sorted([iniciador_id, complice_id, victima_id])
        cursor.execute("SELECT UserID FROM RoboStats WHERE UserID = ANY(%s) FOR UPDATE", (ids_stats,))

        init_level, init_xp, init_last, init_success, init_fail_consec = _get_thief_stats(cursor, iniciador_id)
        comp_level, comp_xp, comp_last, comp_success, comp_fail_consec = _get_thief_stats(cursor, complice_id)

        if init_last and init_last.tzinfo is not None:
            init_last = init_last.replace(tzinfo=None)
        if comp_last and comp_last.tzinfo is not None:
            comp_last = comp_last.replace(tzinfo=None)

        init_cooldown = get_cooldown_minutes(init_level)
        comp_cooldown = get_cooldown_minutes(comp_level)

        # Verificar cooldown del iniciador
        if init_last and ahora_db - init_last < timedelta(minutes=init_cooldown):
            tiempo_restante = init_last + timedelta(minutes=init_cooldown) - ahora_db
            return 'cooldown', {'user': 'iniciador', 'tiempo_restante': tiempo_restante}

        # Verificar cooldown del cómplice
        if comp_last and ahora_db - comp_last < timedelta(minutes=comp_cooldown):
            tiempo_restante = comp_last + timedelta(minutes=comp_cooldown) - ahora_db
            return 'cooldown', {'user': 'complice', 'tiempo_restante': tiempo_restante}

        # Bloquear y obtener saldos de Users
        ids_users = sorted([iniciador_id, complice_id, victima_id])
        cursor.execute("SELECT UserID, Balance FROM Users WHERE UserID = ANY(%s) FOR UPDATE", (ids_users,))
        rows = cursor.fetchall()
        if len(rows) != 3:
            raise ValueError("No se pudieron obtener los saldos de todos los usuarios.")

        saldos = {row[0]: row[1] for row in rows}
        saldo_iniciador = saldos[iniciador_id]
        saldo_complice = saldos[complice_id]
        saldo_victima = saldos[victima_id]

        if saldo_victima < VICTIMA_MIN_SALDO:
            return 'no_money', {}

        # Verificar Escudo de la víctima
        cursor.execute("SELECT ShieldExpiry FROM RoboStats WHERE UserID = %s", (victima_id,))
        res_shield = cursor.fetchone()
        shield_expiry = res_shield[0] if res_shield else None
        if shield_expiry and shield_expiry.tzinfo is not None:
            shield_expiry = shield_expiry.replace(tzinfo=None)
        if shield_expiry and ahora_db < shield_expiry:
            return 'shield_active', {'tiempo_restante': shield_expiry - ahora_db}

        # Verificar protección tras robo de la víctima
        protection_minutes = get_protection_minutes(victima_id)
        cursor.execute("SELECT LastRobadoTime FROM RoboStats WHERE UserID = %s", (victima_id,))
        last_robado = cursor.fetchone()[0]
        if last_robado and last_robado.tzinfo is not None:
            last_robado = last_robado.replace(tzinfo=None)
        if last_robado and ahora_db - last_robado < timedelta(minutes=protection_minutes):
            return 'protection', {'tiempo_restante': (last_robado + timedelta(minutes=protection_minutes) - ahora_db), 'protection_minutes': protection_minutes}

        # ============================================================
        # CÁLCULO DE PROBABILIDAD COMBINADA Y PARÁMETROS
        # ============================================================
        # Calculamos la probabilidad individual del iniciador vs la víctima
        robo_params = calcular_robo_dinamico(saldo_iniciador, saldo_victima, init_level)
        prob_exito = robo_params["prob_exito"]

        # Aplicar bonus de robos exitosos del iniciador
        if init_success > 20:
            prob_exito += 5
        elif init_success > 10:
            prob_exito += 3
        elif init_success > 5:
            prob_exito += 1

        # Aplicar mala suerte del iniciador
        bad_luck_init = get_bad_luck_bonus(init_fail_consec)
        prob_exito += bad_luck_init["prob_bonus"]

        # Dificultad dinámica
        cantidad_a_robar_iniciador_temp = int(saldo_victima * (robo_params["porcentaje_robo"] / 100))
        difficulty_modifier, _ = DynamicDifficulty.calculate_dynamic_difficulty(
            iniciador_id, cantidad_a_robar_iniciador_temp, 'robo'
        )
        prob_exito -= int(difficulty_modifier * 15)

        # Sumar el bonus por robo en banda (+15%)
        prob_combinada = prob_exito + 15
        prob_combinada = max(10, min(90, prob_combinada))

        # Registrar intento de robo (actualizar cooldowns de ambos inmediatamente)
        cursor.execute("UPDATE RoboStats SET LastRoboTime = CURRENT_TIMESTAMP WHERE UserID IN (%s, %s)", (iniciador_id, complice_id))

        # Determinar resultado
        exito = random.randint(1, 100) <= int(prob_combinada)

        if exito:
            # Botín total robado de la víctima se basa en el porcentaje del iniciador
            porcentaje = robo_params["porcentaje_robo"]
            cantidad_total_robada = int(saldo_victima * (porcentaje / 100))
            cantidad_total_robada = max(1, cantidad_total_robada)

            # Se reparte 50/50
            split_base = cantidad_total_robada // 2

            # Cada uno obtiene su split + su bonus de nivel individual
            init_bonuses = get_thief_bonuses(init_level)
            comp_bonuses = get_thief_bonuses(comp_level)

            bonus_loot_init = int(split_base * init_bonuses["loot_bonus_pct"])
            total_init = split_base + bonus_loot_init

            bonus_loot_comp = int(split_base * comp_bonuses["loot_bonus_pct"])
            total_comp = split_base + bonus_loot_comp

            # Actualizar saldos en la base de datos
            cursor.execute("UPDATE Users SET Balance = Balance - %s WHERE UserID = %s RETURNING Balance", (cantidad_total_robada, victima_id))
            nuevo_saldo_victima = cursor.fetchone()[0]

            cursor.execute("UPDATE Users SET Balance = Balance + %s WHERE UserID = %s RETURNING Balance", (total_init, iniciador_id))
            nuevo_saldo_init = cursor.fetchone()[0]

            cursor.execute("UPDATE Users SET Balance = Balance + %s WHERE UserID = %s RETURNING Balance", (total_comp, complice_id))
            nuevo_saldo_comp = cursor.fetchone()[0]

            # Transacciones
            cursor.execute("""
                INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            """, (iniciador_id, total_init, f"Robo en Banda (Éxito) vs {victima_name}"))
            cursor.execute("""
                INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            """, (complice_id, total_comp, f"Robo en Banda (Éxito) vs {victima_name}"))
            cursor.execute("""
                INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            """, (victima_id, -cantidad_total_robada, f"Robado en Banda por {iniciador_name} y {complice_name}"))

            # XP y estadísticas de robo para el iniciador
            xp_ganada_init = calc_xp_from_robbery(split_base)
            xp_res_init = apply_thief_xp(init_level, init_xp, xp_ganada_init)
            cursor.execute("""
                UPDATE RoboStats SET 
                RobosExitosos = COALESCE(RobosExitosos, 0) + 1,
                RobosFallidosConsecutivos = 0,
                TotalRobado = COALESCE(TotalRobado, 0) + %s,
                ThiefLevel = %s,
                ThiefXP = %s
                WHERE UserID = %s
            """, (split_base, xp_res_init["level"], xp_res_init["xp"], iniciador_id))

            # XP y estadísticas de robo para el cómplice
            xp_ganada_comp = calc_xp_from_robbery(split_base)
            xp_res_comp = apply_thief_xp(comp_level, comp_xp, xp_ganada_comp)
            cursor.execute("""
                UPDATE RoboStats SET 
                RobosExitosos = COALESCE(RobosExitosos, 0) + 1,
                RobosFallidosConsecutivos = 0,
                TotalRobado = COALESCE(TotalRobado, 0) + %s,
                ThiefLevel = %s,
                ThiefXP = %s
                WHERE UserID = %s
            """, (split_base, xp_res_comp["level"], xp_res_comp["xp"], complice_id))

            # Estadísticas de la víctima
            cursor.execute("""
                UPDATE RoboStats SET 
                TotalPerdido = COALESCE(TotalPerdido, 0) + %s,
                LastRobadoTime = CURRENT_TIMESTAMP
                WHERE UserID = %s
            """, (cantidad_total_robada, victima_id))

            # Registrar logs
            cursor.execute("""
                INSERT INTO RoboLog (LadronID, VictimaID, CantidadRobada, Exitoso)
                VALUES (%s, %s, %s, TRUE)
            """, (iniciador_id, victima_id, split_base))
            cursor.execute("""
                INSERT INTO RoboLog (LadronID, VictimaID, CantidadRobada, Exitoso)
                VALUES (%s, %s, %s, TRUE)
            """, (complice_id, victima_id, split_base))

            return 'success', {
                'cantidad_total_robada': cantidad_total_robada,
                'split_base': split_base,
                'iniciador': {
                    'total_ganado': total_init,
                    'bonus_loot': bonus_loot_init,
                    'nuevo_saldo': nuevo_saldo_init,
                    'xp_ganada': xp_ganada_init,
                    'level': xp_res_init["level"],
                    'xp': xp_res_init["xp"],
                    'xp_for_next': xp_res_init["xp_for_next"],
                    'leveled_up': xp_res_init["leveled_up"],
                    'previous_level': xp_res_init["previous_level"],
                    'rank': xp_res_init["rank"],
                    'cooldown_minutes': get_cooldown_minutes(xp_res_init["level"])
                },
                'complice': {
                    'total_ganado': total_comp,
                    'bonus_loot': bonus_loot_comp,
                    'nuevo_saldo': nuevo_saldo_comp,
                    'xp_ganada': xp_ganada_comp,
                    'level': xp_res_comp["level"],
                    'xp': xp_res_comp["xp"],
                    'xp_for_next': xp_res_comp["xp_for_next"],
                    'leveled_up': xp_res_comp["leveled_up"],
                    'previous_level': xp_res_comp["previous_level"],
                    'rank': xp_res_comp["rank"],
                    'cooldown_minutes': get_cooldown_minutes(xp_res_comp["level"])
                },
                'nuevo_saldo_victima': nuevo_saldo_victima,
                'protection_minutes': protection_minutes,
                'prob_exito_final': int(prob_combinada),
                'tier_emoji': robo_params["tier_emoji"],
                'tier_nombre': robo_params["tier_nombre"]
            }

        else:
            # Fallo: multa individual calculada para cada uno sobre su propio saldo
            # Calculamos los parámetros del robo dinámico por separado
            robo_params_init = calcular_robo_dinamico(saldo_iniciador, saldo_victima, init_level)
            robo_params_comp = calcular_robo_dinamico(saldo_complice, saldo_victima, comp_level)

            bad_luck_init = get_bad_luck_bonus(init_fail_consec)
            bad_luck_comp = get_bad_luck_bonus(comp_fail_consec)

            # Multa iniciador
            cantidad_init_temp = int(saldo_victima * (robo_params_init["porcentaje_robo"] / 100))
            penalizacion_init = int(cantidad_init_temp * (robo_params_init["penalizacion_pct"] / 100))
            penalizacion_init = int(penalizacion_init * bad_luck_init["penalty_mult"])
            penalizacion_init = min(penalizacion_init, saldo_iniciador)

            # Multa cómplice
            cantidad_comp_temp = int(saldo_victima * (robo_params_comp["porcentaje_robo"] / 100))
            penalizacion_comp = int(cantidad_comp_temp * (robo_params_comp["penalizacion_pct"] / 100))
            penalizacion_comp = int(penalizacion_comp * bad_luck_comp["penalty_mult"])
            penalizacion_comp = min(penalizacion_comp, saldo_complice)

            nuevo_saldo_init = saldo_iniciador - penalizacion_init
            nuevo_saldo_comp = saldo_complice - penalizacion_comp

            if penalizacion_init > 0:
                cursor.execute("UPDATE Users SET Balance = %s WHERE UserID = %s", (nuevo_saldo_init, iniciador_id))
                cursor.execute("""
                    INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                """, (iniciador_id, -penalizacion_init, "Multa por intento de robo en banda (Iniciador)"))

            if penalizacion_comp > 0:
                cursor.execute("UPDATE Users SET Balance = %s WHERE UserID = %s", (nuevo_saldo_comp, complice_id))
                cursor.execute("""
                    INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                """, (complice_id, -penalizacion_comp, "Multa por intento de robo en banda (Cómplice)"))

            # Pérdida de XP individual
            xp_perdida_init = calc_xp_from_robbery(cantidad_init_temp)
            xp_res_init = remove_thief_xp(init_level, init_xp, xp_perdida_init)

            xp_perdida_comp = calc_xp_from_robbery(cantidad_comp_temp)
            xp_res_comp = remove_thief_xp(comp_level, comp_xp, xp_perdida_comp)

            # Registrar LastRoboTime con cooldown reducido por fallo
            init_cooldown_actual = get_cooldown_minutes(xp_res_init["level"])
            init_reduccion = int(init_cooldown_actual * 60 * (1 - FAIL_COOLDOWN_FACTOR))
            cursor.execute("""
                UPDATE RoboStats SET 
                RobosFallidos = COALESCE(RobosFallidos, 0) + 1,
                RobosFallidosConsecutivos = COALESCE(RobosFallidosConsecutivos, 0) + 1,
                TotalPerdido = COALESCE(TotalPerdido, 0) + %s,
                ThiefLevel = %s,
                ThiefXP = %s,
                LastRoboTime = CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                WHERE UserID = %s
            """, (penalizacion_init, xp_res_init["level"], xp_res_init["xp"], init_reduccion, iniciador_id))

            comp_cooldown_actual = get_cooldown_minutes(xp_res_comp["level"])
            comp_reduccion = int(comp_cooldown_actual * 60 * (1 - FAIL_COOLDOWN_FACTOR))
            cursor.execute("""
                UPDATE RoboStats SET 
                RobosFallidos = COALESCE(RobosFallidos, 0) + 1,
                RobosFallidosConsecutivos = COALESCE(RobosFallidosConsecutivos, 0) + 1,
                TotalPerdido = COALESCE(TotalPerdido, 0) + %s,
                ThiefLevel = %s,
                ThiefXP = %s,
                LastRoboTime = CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                WHERE UserID = %s
            """, (penalizacion_comp, xp_res_comp["level"], xp_res_comp["xp"], comp_reduccion, complice_id))

            # Registrar logs
            cursor.execute("""
                INSERT INTO RoboLog (LadronID, VictimaID, CantidadRobada, Exitoso)
                VALUES (%s, %s, 0, FALSE)
            """, (iniciador_id, victima_id))
            cursor.execute("""
                INSERT INTO RoboLog (LadronID, VictimaID, CantidadRobada, Exitoso)
                VALUES (%s, %s, 0, FALSE)
            """, (complice_id, victima_id))

            return 'fail', {
                'iniciador': {
                    'penalizacion': penalizacion_init,
                    'nuevo_saldo': nuevo_saldo_init,
                    'xp_perdida': xp_res_init["xp_lost"],
                    'level': xp_res_init["level"],
                    'xp': xp_res_init["xp"],
                    'xp_for_next': xp_res_init["xp_for_next"],
                    'leveled_down': xp_res_init["leveled_down"],
                    'previous_level': xp_res_init["previous_level"],
                    'rank': xp_res_init["rank"],
                    'cooldown_minutes': int(init_cooldown_actual * FAIL_COOLDOWN_FACTOR),
                    'bad_luck_desc': bad_luck_init["descripcion"],
                    'fallos_consecutivos': init_fail_consec + 1
                },
                'complice': {
                    'penalizacion': penalizacion_comp,
                    'nuevo_saldo': nuevo_saldo_comp,
                    'xp_perdida': xp_res_comp["xp_lost"],
                    'level': xp_res_comp["level"],
                    'xp': xp_res_comp["xp"],
                    'xp_for_next': xp_res_comp["xp_for_next"],
                    'leveled_down': xp_res_comp["leveled_down"],
                    'previous_level': xp_res_comp["previous_level"],
                    'rank': xp_res_comp["rank"],
                    'cooldown_minutes': int(comp_cooldown_actual * FAIL_COOLDOWN_FACTOR),
                    'bad_luck_desc': bad_luck_comp["descripcion"],
                    'fallos_consecutivos': comp_fail_consec + 1
                },
                'prob_exito_final': int(prob_combinada),
                'tier_emoji': robo_params["tier_emoji"],
                'tier_nombre': robo_params["tier_nombre"]
            }

def _ejecutar_robo_banco_db(iniciador_id, complice_id=None, iniciador_name="", complice_name=""):
    """
    Realiza la lógica de base de datos para el Robo al Banco Central.
    Soporta robo individual o robo en banda (si complice_id no es None).
    """
    ensure_user(iniciador_id, iniciador_name)
    if complice_id:
        ensure_user(complice_id, complice_name)

    with db_cursor() as cursor:
        cursor.execute("SELECT NOW()")
        ahora_db = cursor.fetchone()[0]
        if ahora_db and ahora_db.tzinfo is not None:
            ahora_db = ahora_db.replace(tzinfo=None)

        # Inicializar estadísticas
        cursor.execute("INSERT INTO RoboStats (UserID) VALUES (%s) ON CONFLICT (UserID) DO NOTHING", (iniciador_id,))
        if complice_id:
            cursor.execute("INSERT INTO RoboStats (UserID) VALUES (%s) ON CONFLICT (UserID) DO NOTHING", (complice_id,))

        # Bloquear RoboStats
        ids_stats = sorted([iniciador_id] + ([complice_id] if complice_id else []))
        cursor.execute("SELECT UserID FROM RoboStats WHERE UserID = ANY(%s) FOR UPDATE", (ids_stats,))

        init_level, init_xp, _, _, _ = _get_thief_stats(cursor, iniciador_id)
        # Check level 10+
        if init_level < 10:
            return 'level_low', {'user': 'iniciador', 'level': init_level}

        # Check LastBancoRoboTime
        cursor.execute("SELECT LastBancoRoboTime FROM RoboStats WHERE UserID = %s", (iniciador_id,))
        init_last_banco = cursor.fetchone()[0]
        if init_last_banco and init_last_banco.tzinfo is not None:
            init_last_banco = init_last_banco.replace(tzinfo=None)
        if init_last_banco and ahora_db - init_last_banco < timedelta(hours=24):
            tiempo_restante = init_last_banco + timedelta(hours=24) - ahora_db
            return 'cooldown', {'user': 'iniciador', 'tiempo_restante': tiempo_restante}

        if complice_id:
            comp_level, comp_xp, _, _, _ = _get_thief_stats(cursor, complice_id)
            if comp_level < 10:
                return 'level_low', {'user': 'complice', 'level': comp_level}
            cursor.execute("SELECT LastBancoRoboTime FROM RoboStats WHERE UserID = %s", (complice_id,))
            comp_last_banco = cursor.fetchone()[0]
            if comp_last_banco and comp_last_banco.tzinfo is not None:
                comp_last_banco = comp_last_banco.replace(tzinfo=None)
            if comp_last_banco and ahora_db - comp_last_banco < timedelta(hours=24):
                tiempo_restante = comp_last_banco + timedelta(hours=24) - ahora_db
                return 'cooldown', {'user': 'complice', 'tiempo_restante': tiempo_restante}

        # Lock BancoCentral
        cursor.execute("SELECT Reservas FROM BancoCentral WHERE ID = 1 FOR UPDATE")
        reservas = cursor.fetchone()[0]

        if reservas <= 0:
            return 'no_bank_reserves', {}

        # Lock Users balances
        ids_users = sorted([iniciador_id] + ([complice_id] if complice_id else []))
        cursor.execute("SELECT UserID, Balance FROM Users WHERE UserID = ANY(%s) FOR UPDATE", (ids_users,))
        rows = cursor.fetchall()
        saldos = {row[0]: row[1] for row in rows}
        saldo_iniciador = saldos[iniciador_id]
        saldo_complice = saldos.get(complice_id, 0)

        # Calcular éxito:
        # prob_exito = min(35, 10 + (thief_level - 10) * 1.7)
        prob_iniciador = min(35, 10 + (init_level - 10) * 1.7)
        if complice_id:
            prob_combinada = prob_iniciador + 15
            prob_combinada = max(10, min(90, prob_combinada))
        else:
            prob_combinada = prob_iniciador
            prob_combinada = max(10, min(90, prob_combinada))

        # Registrar intento de robo (actualizar cooldown de 24 horas)
        cursor.execute("UPDATE RoboStats SET LastBancoRoboTime = CURRENT_TIMESTAMP WHERE UserID = %s", (iniciador_id,))
        if complice_id:
            cursor.execute("UPDATE RoboStats SET LastBancoRoboTime = CURRENT_TIMESTAMP WHERE UserID = %s", (complice_id,))

        exito = random.randint(1, 100) <= int(prob_combinada)

        if exito:
            # Botín aleatorio de 200.000 a 1.000.000
            botin_potencial = random.randint(200000, 1000000)
            botin_robado = min(botin_potencial, reservas)

            # Descontar del banco de forma defensiva asegurando no bajar de 0
            cursor.execute("UPDATE BancoCentral SET Reservas = Reservas - %s WHERE ID = 1 AND Reservas >= %s", (botin_robado, botin_robado))
            if cursor.rowcount == 0:
                # Si falló por concurrencia o cambio de saldo, tomamos lo que quede
                cursor.execute("SELECT Reservas FROM BancoCentral WHERE ID = 1 FOR UPDATE")
                reservas_restantes = cursor.fetchone()[0]
                botin_robado = max(0, reservas_restantes)
                cursor.execute("UPDATE BancoCentral SET Reservas = Reservas - %s WHERE ID = 1", (botin_robado,))

            if complice_id:
                # Splitear 50/50 sin bonus de botín por nivel
                split_base = botin_robado // 2
                resto = botin_robado - split_base

                cursor.execute("UPDATE Users SET Balance = Balance + %s WHERE UserID = %s", (split_base, iniciador_id))
                cursor.execute("UPDATE Users SET Balance = Balance + %s WHERE UserID = %s", (resto, complice_id))

                cursor.execute("""
                    INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                    VALUES (%s, %s, 'Robo al Banco Central (Éxito)', CURRENT_TIMESTAMP)
                """, (iniciador_id, split_base))
                cursor.execute("""
                    INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                    VALUES (%s, %s, 'Robo al Banco Central (Éxito)', CURRENT_TIMESTAMP)
                """, (complice_id, resto))

                # Registrar logs
                cursor.execute("INSERT INTO RoboLog (LadronID, VictimaID, CantidadRobada, Exitoso) VALUES (%s, 1, %s, TRUE)", (iniciador_id, split_base))
                cursor.execute("INSERT INTO RoboLog (LadronID, VictimaID, CantidadRobada, Exitoso) VALUES (%s, 1, %s, TRUE)", (complice_id, resto))

                # XP ganada
                xp_ganada_init = calc_xp_from_robbery(split_base)
                xp_res_init = apply_thief_xp(init_level, init_xp, xp_ganada_init)
                cursor.execute("UPDATE RoboStats SET ThiefLevel = %s, ThiefXP = %s, RobosExitosos = COALESCE(RobosExitosos, 0) + 1, TotalRobado = COALESCE(TotalRobado, 0) + %s WHERE UserID = %s", 
                               (xp_res_init["level"], xp_res_init["xp"], split_base, iniciador_id))

                comp_level, comp_xp, _, _, _ = _get_thief_stats(cursor, complice_id)
                xp_ganada_comp = calc_xp_from_robbery(resto)
                xp_res_comp = apply_thief_xp(comp_level, comp_xp, xp_ganada_comp)
                cursor.execute("UPDATE RoboStats SET ThiefLevel = %s, ThiefXP = %s, RobosExitosos = COALESCE(RobosExitosos, 0) + 1, TotalRobado = COALESCE(TotalRobado, 0) + %s WHERE UserID = %s", 
                               (xp_res_comp["level"], xp_res_comp["xp"], resto, complice_id))

                return 'success', {
                    'botin_robado': botin_robado,
                    'es_banda': True,
                    'iniciador': {
                        'ganancia': split_base,
                        'xp_ganada': xp_ganada_init,
                        'level': xp_res_init["level"],
                        'leveled_up': xp_res_init["leveled_up"],
                        'previous_level': xp_res_init["previous_level"],
                        'rank': xp_res_init["rank"],
                        'xp': xp_res_init["xp"],
                        'xp_for_next': xp_res_init["xp_for_next"]
                    },
                    'complice': {
                        'ganancia': resto,
                        'xp_ganada': xp_ganada_comp,
                        'level': xp_res_comp["level"],
                        'leveled_up': xp_res_comp["leveled_up"],
                        'previous_level': xp_res_comp["previous_level"],
                        'rank': xp_res_comp["rank"],
                        'xp': xp_res_comp["xp"],
                        'xp_for_next': xp_res_comp["xp_for_next"]
                    },
                    'prob_exito': int(prob_combinada)
                }
            else:
                # Individual
                cursor.execute("UPDATE Users SET Balance = Balance + %s WHERE UserID = %s", (botin_robado, iniciador_id))
                cursor.execute("""
                    INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                    VALUES (%s, %s, 'Robo al Banco Central (Éxito)', CURRENT_TIMESTAMP)
                """, (iniciador_id, botin_robado))
                cursor.execute("INSERT INTO RoboLog (LadronID, VictimaID, CantidadRobada, Exitoso) VALUES (%s, 1, %s, TRUE)", (iniciador_id, botin_robado))

                xp_ganada = calc_xp_from_robbery(botin_robado)
                xp_res = apply_thief_xp(init_level, init_xp, xp_ganada)
                cursor.execute("UPDATE RoboStats SET ThiefLevel = %s, ThiefXP = %s, RobosExitosos = COALESCE(RobosExitosos, 0) + 1, TotalRobado = COALESCE(TotalRobado, 0) + %s WHERE UserID = %s", 
                               (xp_res["level"], xp_res["xp"], botin_robado, iniciador_id))

                return 'success', {
                    'botin_robado': botin_robado,
                    'es_banda': False,
                    'iniciador': {
                        'ganancia': botin_robado,
                        'xp_ganada': xp_ganada,
                        'level': xp_res["level"],
                        'leveled_up': xp_res["leveled_up"],
                        'previous_level': xp_res["previous_level"],
                        'rank': xp_res["rank"],
                        'xp': xp_res["xp"],
                        'xp_for_next': xp_res["xp_for_next"]
                    },
                    'prob_exito': int(prob_combinada)
                }

        else:
            # Fallo: multa fija de 50.000 por ladrón
            multa_fija = 50000
            multa_init = min(multa_fija, saldo_iniciador)
            
            # Cobrar multa al iniciador
            if multa_init > 0:
                cursor.execute("UPDATE Users SET Balance = Balance - %s WHERE UserID = %s", (multa_init, iniciador_id))
                cursor.execute("""
                    INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                    VALUES (%s, %s, 'Multa por Robo al Banco Central (Fallo)', CURRENT_TIMESTAMP)
                """, (iniciador_id, -multa_init))
                cursor.execute("UPDATE BancoCentral SET Reservas = Reservas + %s WHERE ID = 1", (multa_init,))

            xp_perdida_init = calc_xp_from_robbery(multa_init)
            xp_res_init = remove_thief_xp(init_level, init_xp, xp_perdida_init)
            cursor.execute("UPDATE RoboStats SET ThiefLevel = %s, ThiefXP = %s, RobosFallidos = COALESCE(RobosFallidos, 0) + 1, TotalPerdido = COALESCE(TotalPerdido, 0) + %s WHERE UserID = %s",
                           (xp_res_init["level"], xp_res_init["xp"], multa_init, iniciador_id))

            # Registrar log
            cursor.execute("INSERT INTO RoboLog (LadronID, VictimaID, CantidadRobada, Exitoso) VALUES (%s, 1, 0, FALSE)", (iniciador_id,))

            multa_comp = 0
            xp_res_comp = None
            if complice_id:
                multa_comp = min(multa_fija, saldo_complice)
                if multa_comp > 0:
                    cursor.execute("UPDATE Users SET Balance = Balance - %s WHERE UserID = %s", (multa_comp, complice_id))
                    cursor.execute("""
                        INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                        VALUES (%s, %s, 'Multa por Robo al Banco Central (Fallo)', CURRENT_TIMESTAMP)
                    """, (complice_id, -multa_comp))
                    cursor.execute("UPDATE BancoCentral SET Reservas = Reservas + %s WHERE ID = 1", (multa_comp,))

                comp_level, comp_xp, _, _, _ = _get_thief_stats(cursor, complice_id)
                xp_perdida_comp = calc_xp_from_robbery(multa_comp)
                xp_res_comp = remove_thief_xp(comp_level, comp_xp, xp_perdida_comp)
                cursor.execute("UPDATE RoboStats SET ThiefLevel = %s, ThiefXP = %s, RobosFallidos = COALESCE(RobosFallidos, 0) + 1, TotalPerdido = COALESCE(TotalPerdido, 0) + %s WHERE UserID = %s",
                               (xp_res_comp["level"], xp_res_comp["xp"], multa_comp, complice_id))
                
                cursor.execute("INSERT INTO RoboLog (LadronID, VictimaID, CantidadRobada, Exitoso) VALUES (%s, 1, 0, FALSE)", (complice_id,))

            return 'fail', {
                'es_banda': bool(complice_id),
                'iniciador': {
                    'penalizacion': multa_init,
                    'xp_perdida': xp_res_init["xp_lost"],
                    'level': xp_res_init["level"],
                    'rank': xp_res_init["rank"],
                    'xp': xp_res_init["xp"],
                    'xp_for_next': xp_res_init["xp_for_next"]
                },
                'complice': {
                    'penalizacion': multa_comp,
                    'xp_perdida': xp_res_comp["xp_lost"] if xp_res_comp else 0,
                    'level': xp_res_comp["level"] if xp_res_comp else 1,
                    'rank': xp_res_comp["rank"] if xp_res_comp else "Carterista",
                    'xp': xp_res_comp["xp"] if xp_res_comp else 0,
                    'xp_for_next': xp_res_comp["xp_for_next"] if xp_res_comp else 0
                } if complice_id else None,
                'prob_exito': int(prob_combinada)
            }

class Robar(commands.Cog):
    """Cog para el comando de robar dinero a otros usuarios."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="perfil_ladron", description="Muestra tu nivel, rango y bonificaciones como ladrón.")
    async def perfil_ladron_cmd(self, interaction: discord.Interaction):
        await self._perfil_ladron_logica(interaction)

    @commands.command(name="perfil_ladron", help="Muestra tu nivel, rango y bonificaciones como ladrón. Uso: !perfil_ladron")
    async def perfil_ladron(self, ctx):
        await self._perfil_ladron_logica(ctx)

    async def _normalize_context(self, ctx_or_interaction, ephemeral: bool = True, defer: bool = True) -> tuple[discord.abc.User, typing.Callable[..., typing.Awaitable[typing.Any]], dict]:
        """Normaliza ctx y discord.Interaction para obtener actor y función de envío."""
        if isinstance(ctx_or_interaction, discord.Interaction):
            if defer and not ctx_or_interaction.response.is_done():
                await ctx_or_interaction.response.defer(ephemeral=ephemeral)
            actor = ctx_or_interaction.user
            send_func = ctx_or_interaction.followup.send if ctx_or_interaction.response.is_done() else ctx_or_interaction.response.send_message
            send_kwargs = {"ephemeral": ephemeral}
        else:
            actor = ctx_or_interaction.author
            send_func = ctx_or_interaction.send
            send_kwargs = {}
        return actor, send_func, send_kwargs

    async def _perfil_ladron_logica(self, ctx_or_interaction):
        user, send_func, send_kwargs = await self._normalize_context(ctx_or_interaction, ephemeral=True, defer=True)
        user_id = user.id

        def _get_profile():
            with db_cursor() as c:
                c.execute("""
                    INSERT INTO RoboStats (UserID) VALUES (%s) ON CONFLICT (UserID) DO NOTHING
                """, (user_id,))
                c.execute("""
                    SELECT COALESCE(ThiefLevel, 1), COALESCE(ThiefXP, 0),
                           COALESCE(RobosExitosos, 0), COALESCE(RobosFallidos, 0),
                           COALESCE(TotalRobado, 0), COALESCE(TotalPerdido, 0)
                    FROM RoboStats WHERE UserID = %s
                """, (user_id,))
                return c.fetchone()

        row = await asyncio.to_thread(_get_profile)
        level, xp, exitosos, fallidos, total_robado, total_perdido = row
        bonuses = get_thief_bonuses(level)
        xp_needed = calc_xp_needed(level)
        rank = get_rank_name(level)

        embed = discord.Embed(
            title=f"🥷 Perfil de Ladrón — {user.display_name}",
            description=f"**{rank}** · Nivel **{level}**",
            color=discord.Color.dark_grey()
        )

        if xp_needed > 0:
            bar = format_progress_bar(xp, xp_needed)
            embed.add_field(
                name="Experiencia",
                value=f"`{bar}`\n{xp:,} / {xp_needed:,} XP\n*+10% del botín al tener éxito · -10% al fallar*",
                inline=False
            )
        else:
            embed.add_field(name="Experiencia", value="Nivel máximo alcanzado", inline=False)

        embed.add_field(name="Robos Exitosos", value=f"{exitosos:,}", inline=True)
        embed.add_field(name="Robos Fallidos", value=f"{fallidos:,}", inline=True)
        embed.add_field(name="Total Robado", value=f"{total_robado:,} monedas", inline=True)
        embed.add_field(name="Total Perdido (multas)", value=f"{total_perdido:,} monedas", inline=True)

        embed.add_field(
            name="Bonificaciones Actuales",
            value=(
                f"• +{bonuses['prob_bonus']}% probabilidad de éxito\n"
                f"• +{int(bonuses['loot_bonus_pct'] * 100)}% botín extra\n"
                f"• -{int(bonuses['penalty_reduction'] * 100)}% multas por fallo\n"
                f"• Cooldown: **{get_cooldown_minutes(level):.0f}** min (base {ROBO_COOLDOWN_MINUTES} min)"
            ),
            inline=False
        )

        next_milestone = next((lvl for lvl in sorted(THIEF_MILESTONES) if lvl > level), None)
        if next_milestone:
            embed.add_field(
                name=f"Próximo Hito (Nv. {next_milestone})",
                value=THIEF_MILESTONES[next_milestone],
                inline=False
            )

        embed.add_field(
            name="💡 Sistema Dinámico",
            value=(
                "El % de robo y probabilidad se calculan automáticamente según "
                "la diferencia de riqueza con tu víctima.\n"
                "• 💎 Robar a ricos → Alto botín, baja probabilidad\n"
                "• 🐀 Robar a pobres → Poco botín, alta penalización"
            ),
            inline=False
        )

        await send_func(embed=embed, **send_kwargs)

    @app_commands.command(name="robar", description="Intenta robar dinero a otro usuario")
    @app_commands.describe(
        victima="Usuario al que intentarás robar"
    )
    @ECONOMY_COOLDOWN
    async def robar_slash(self, interaction: discord.Interaction, victima: discord.Member):
        await self._robar_logica(interaction, victima, is_slash=True)
    
    @commands.command(name="robar", help="Intenta robar dinero a otro usuario. Uso: !robar @usuario")
    async def robar(self, ctx, victima: discord.Member):
        await self._robar_logica(ctx, victima, is_slash=False)
    
    async def _robar_logica(self, ctx_or_interaction, victima: discord.Member, is_slash: bool = False):
        """Lógica principal del comando robar."""
        ladron, send_func, send_kwargs = await self._normalize_context(ctx_or_interaction, ephemeral=True, defer=False)
        
        ladron_id = ladron.id
        ladron_name = ladron.name
        victima_id = victima.id
        victima_name = victima.name
        
        # Validaciones iniciales
        if victima.bot:
            await send_func("❌ No puedes robar a un bot.", **send_kwargs)
            return
            
        if ladron_id == victima_id:
            await send_func("❌ No puedes robarte a ti mismo.", **send_kwargs)
            return
            
        try:
            # Ejecutar validaciones y lógica de robo en base de datos en un hilo secundario PRIMERO
            status, data = await asyncio.to_thread(
                _ejecutar_robo_db, ladron_id, victima_id, ladron_name, victima_name
            )
            
            if status == 'cooldown':
                tr = data['tiempo_restante']
                tiempo_str = _format_timedelta(tr, show_seconds=True)
                await send_func(f"⏰ Debes esperar {tiempo_str} para intentar robar nuevamente.", **send_kwargs)
                return
                
            if status == 'shield_active':
                tr = data['tiempo_restante']
                tiempo_str = _format_timedelta(tr, show_seconds=False)
                await send_func(f"🛡️🌟 {victima.mention} tiene un **Escudo Total** activo. Es inmune a robos por {tiempo_str} más.", **send_kwargs)
                return

            if status == 'protection':
                tr = data['tiempo_restante']
                tiempo_str = _format_timedelta(tr, show_seconds=False)
                prot_m = data['protection_minutes']
                await send_func(f"🛡️ {victima.mention} tiene protección por {tiempo_str} más (protección de {prot_m} min tras robo).", **send_kwargs)
                return
                
            if status == 'no_money':
                await send_func(f"❌ {victima.mention} no tiene suficiente dinero para robarle (mínimo {VICTIMA_MIN_SALDO:,} monedas).", **send_kwargs)
                return
            
            # Si llegamos aquí, el robo fue success o fail y la base de datos ya se actualizó.
            # Procedemos a enviar el mensaje público de preparación y la animación.
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.response.defer(ephemeral=False)
                send_func = ctx_or_interaction.followup.send
                send_kwargs = {"ephemeral": False}
                msg = await send_func("🕵️ Analizando al objetivo... calculando el plan...", **send_kwargs)
            else:
                msg = await ctx_or_interaction.send("🕵️ Analizando al objetivo... calculando el plan...")
            
            # Obtener parámetros dinámicos del robo para el embed
            robo_params = data['robo_params']
            
            # Mostrar preparación animada con info del tier
            embed_preparacion = discord.Embed(
                title="🕵️ Intento de Robo",
                description=f"{ladron.mention} intenta robar a {victima.mention}...",
                color=discord.Color.gold()
            )
            embed_preparacion.add_field(
                name=f"{robo_params['tier_emoji']} Tipo: {robo_params['tier_nombre']}",
                value=robo_params['tier_desc'],
                inline=False
            )
            embed_preparacion.add_field(
                name="📊 Análisis",
                value=(
                    f"Botín estimado: **{robo_params['porcentaje_robo']}%** del saldo\n"
                    f"Probabilidad de éxito: ~**{data['prob_exito_final']}%**"
                ),
                inline=False
            )
            embed_preparacion.add_field(name="🔍 Estado", value="🕵️ Reconociendo el terreno...", inline=False)
            estado_field_index = len(embed_preparacion.fields) - 1
            await msg.edit(content=None, embed=embed_preparacion)
            
            await asyncio.sleep(2)
            embed_preparacion.set_field_at(estado_field_index, name="🔍 Estado", value="🏃 Calculando rutas de escape...", inline=False)
            await msg.edit(embed=embed_preparacion)
            
            await asyncio.sleep(2)
            
            if status == 'success':
                embed_exito = discord.Embed(
                    title=f"💰 ¡{robo_params['tier_emoji']} {robo_params['tier_nombre']} Exitoso!",
                    description=f"{ladron.mention} ha robado exitosamente a {victima.mention}",
                    color=discord.Color.green()
                )
                embed_exito.add_field(name="Cantidad Robada", value=f"{data['cantidad_a_robar']:,} monedas", inline=True)
                if data.get('bonus_loot', 0) > 0:
                    embed_exito.add_field(
                        name="Bonus de Nivel",
                        value=f"+{data['bonus_loot']:,} monedas",
                        inline=True
                    )
                embed_exito.add_field(name="Total Obtenido", value=f"{data['cantidad_total']:,} monedas", inline=False)
                embed_exito.add_field(name="XP de Ladrón", value=f"+{data['xp_ganada']:,} XP", inline=True)
                embed_exito.add_field(
                    name="Nivel de Ladrón",
                    value=f"**{data['rank']}** (Nv. {data['thief_level']})",
                    inline=True
                )
                if data.get('leveled_up'):
                    embed_exito.add_field(
                        name="🎉 ¡Subiste de Nivel!",
                        value=f"Pasaste del nivel **{data['previous_level']}** al **{data['thief_level']}**.\nNuevo rango: **{data['rank']}**",
                        inline=False
                    )
                elif data.get('xp_for_next', 0) > 0:
                    bar = format_progress_bar(data['thief_xp'], data['xp_for_next'])
                    embed_exito.add_field(
                        name="Progreso",
                        value=f"`{bar}` {data['thief_xp']:,}/{data['xp_for_next']:,} XP",
                        inline=False
                    )
                embed_exito.add_field(name="Nuevo Saldo (Ladrón)", value=f"{data['nuevo_saldo_ladron']:,} monedas", inline=True)
                embed_exito.add_field(name="Nuevo Saldo (Víctima)", value=f"{data['nuevo_saldo_victima']:,} monedas", inline=True)
                embed_exito.set_footer(text=f"{victima_name} tiene protección {data['protection_minutes']} min · Próximo robo en {data['cooldown_minutes']:.0f} min")
                await msg.edit(content=f"🔔 {victima.mention}", embed=embed_exito)
                
            else:  # status == 'fail'
                embed_fracaso = discord.Embed(
                    title=f"🚨 ¡{robo_params['tier_emoji']} {robo_params['tier_nombre']} Fallido!",
                    description=f"{ladron.mention} fue descubierto intentando robar a {victima.mention}",
                    color=discord.Color.red()
                )
                embed_fracaso.add_field(
                    name="Multa por Intento",
                    value=f"{data['penalizacion']:,} monedas ({robo_params['penalizacion_pct']}% del botín)",
                    inline=False
                )
                if data.get('leveled_down'):
                    embed_fracaso.add_field(name="XP Perdida", value=f"-{data['xp_perdida']:,} XP (¡Has bajado de nivel!)", inline=True)
                else:
                    embed_fracaso.add_field(name="XP Perdida", value=f"-{data['xp_perdida']:,} XP (no bajas de nivel en este fallo)", inline=True)
                embed_fracaso.add_field(
                    name="Tu Rango",
                    value=f"**{data['rank']}** (Nv. {data['thief_level']})",
                    inline=True
                )
                if data.get('xp_for_next', 0) > 0:
                    bar = format_progress_bar(data['thief_xp'], data['xp_for_next'])
                    embed_fracaso.add_field(
                        name="Progreso",
                        value=f"`{bar}` {data['thief_xp']:,}/{data['xp_for_next']:,} XP",
                        inline=False
                    )
                # Mostrar bonus de racha de mala suerte si aplica
                bad_luck_desc = data.get('bad_luck_desc')
                next_bad_luck = get_bad_luck_bonus(data.get('fallos_consecutivos', 0))
                if bad_luck_desc:
                    embed_fracaso.add_field(
                        name="🍀 Bonus Activo",
                        value=bad_luck_desc,
                        inline=False
                    )
                elif next_bad_luck and next_bad_luck.get("descripcion"):
                    embed_fracaso.add_field(
                        name="🍀 Próximo Intento",
                        value=next_bad_luck["descripcion"],
                        inline=False
                    )
                embed_fracaso.add_field(name="Nuevo Saldo", value=f"{data['nuevo_saldo_ladron']:,} monedas", inline=True)
                embed_fracaso.set_footer(text=f"Próximo robo en {data['cooldown_minutes']:.0f} min · Usa /perfil_ladron para ver bonificaciones")
                await msg.edit(content=None, embed=embed_fracaso)
                
        except Exception as e:
            logger.error("Error en comando robar", exc_info=True)
            respuesta = "❌ Ocurrió un error al procesar el robo."
            if is_slash:
                try:
                    if not ctx_or_interaction.response.is_done():
                        await ctx_or_interaction.response.send_message(respuesta, ephemeral=True)
                    else:
                        await ctx_or_interaction.followup.send(respuesta, ephemeral=True)
                except Exception:
                    pass
            else:
                await ctx_or_interaction.send(respuesta)

    async def _send_safe_interaction(self, interaction: discord.Interaction, message: str = None, embed: discord.Embed = None, ephemeral: bool = True):
        """Envía un mensaje o embed a la interacción de forma segura sin causar InteractionResponded o NotFound."""
        try:
            if not interaction.response.is_done():
                if embed:
                    await interaction.response.send_message(content=message, embed=embed, ephemeral=ephemeral)
                else:
                    await interaction.response.send_message(content=message, ephemeral=ephemeral)
            else:
                if embed:
                    await interaction.followup.send(content=message, embed=embed, ephemeral=ephemeral)
                else:
                    await interaction.followup.send(content=message, ephemeral=ephemeral)
        except Exception as e:
            logger.warning(f"No se pudo enviar mensaje de interacción: {e}")

    @ECONOMY_COOLDOWN
    async def robar_banda_slash(self, interaction: discord.Interaction, complice: discord.Member, victima: discord.Member):
        ladron = interaction.user
        
        # Validaciones de elegibilidad
        if complice.bot or victima.bot:
            await self._send_safe_interaction(interaction, "❌ No puedes robar con o a un bot.")
            return

        if complice.id == ladron.id:
            await self._send_safe_interaction(interaction, "❌ No puedes ser tu propio cómplice.")
            return

        if victima.id == ladron.id:
            await self._send_safe_interaction(interaction, "❌ No puedes robarte a ti mismo.")
            return

        if complice.id == victima.id:
            await self._send_safe_interaction(interaction, "❌ El cómplice y la víctima no pueden ser la misma persona.")
            return

        # Responder de forma efímera confirmando el envío de la invitación
        await self._send_safe_interaction(
            interaction,
            f"🕵️ Se ha enviado la invitación a {complice.mention} de forma privada. Esperando su respuesta..."
        )

        # Crear y enviar la invitación vía DM al cómplice
        view = RoboBandaInvitationView(initiator=ladron, accomplice=complice, target=victima)
        try:
            msg = await complice.send(
                f"🥷 **Invitación de Robo en Banda**\n"
                f"{ladron.mention} te ha invitado a realizar un golpe conjunto contra {victima.mention}.\n"
                f"Si aceptas, se ejecutará el robo y ambos entrarán en cooldown. El botín se repartirá 50/50.",
                view=view
            )
            view.message = msg
        except discord.Forbidden:
            await self._send_safe_interaction(
                interaction,
                f"❌ No se pudo enviar la invitación a {complice.mention} porque tiene los mensajes privados desactivados."
            )
            return

        # Esperar la respuesta
        await view.wait()

        if not view.accepted:
            await self._send_safe_interaction(
                interaction,
                f"❌ El robo en banda fue cancelado porque {complice.mention} no aceptó la invitación."
            )
            return

        # Si aceptó, ejecutar lógica en BD en un hilo secundario
        try:
            status, data = await asyncio.to_thread(
                _ejecutar_robo_banda_db,
                ladron.id, complice.id, victima.id,
                ladron.name, complice.name, victima.name
            )

            if status == 'cooldown':
                tr = data['tiempo_restante']
                tiempo_str = _format_timedelta(tr, show_seconds=True)
                who = "tú" if data['user'] == 'iniciador' else complice.display_name
                await self._send_safe_interaction(interaction, f"❌ El robo no se pudo realizar porque {who} tiene cooldown activo ({tiempo_str} restantes).")
                try:
                    await complice.send(f"❌ El robo falló porque alguien tiene cooldown activo.")
                except Exception:
                    pass
                return

            if status == 'shield_active':
                tr = data['tiempo_restante']
                tiempo_str = _format_timedelta(tr, show_seconds=False)
                await self._send_safe_interaction(interaction, f"🛡️ {victima.mention} tiene un **Escudo Total** activo ({tiempo_str} restantes).")
                try:
                    await complice.send(f"🛡️ {victima.mention} tiene un **Escudo Total** activo.")
                except Exception:
                    pass
                return

            if status == 'protection':
                tr = data['tiempo_restante']
                tiempo_str = _format_timedelta(tr, show_seconds=False)
                await self._send_safe_interaction(interaction, f"🛡️ {victima.mention} tiene protección contra robos ({tiempo_str} restantes).")
                try:
                    await complice.send(f"🛡️ {victima.mention} tiene protección contra robos.")
                except Exception:
                    pass
                return

            if status == 'no_money':
                await self._send_safe_interaction(interaction, f"❌ {victima.mention} no tiene suficiente dinero (mínimo {VICTIMA_MIN_SALDO:,} monedas).")
                try:
                    await complice.send(f"❌ {victima.mention} no tiene suficiente dinero.")
                except Exception:
                    pass
                return

            # Si es success o fail, notificar de forma privada detallada
            if status == 'success':
                init_data = data['iniciador']
                comp_data = data['complice']

                embed_init = discord.Embed(
                    title=f"💰 ¡{data['tier_emoji']} {data['tier_nombre']} Exitoso!",
                    description=f"El golpe conjunto contra {victima.mention} ha funcionado.",
                    color=discord.Color.green()
                )
                embed_init.add_field(name="Monto base", value=f"{data['split_base']:,} monedas", inline=True)
                embed_init.add_field(name="Bonus por Nivel", value=f"+{init_data['bonus_loot']:,} monedas", inline=True)
                embed_init.add_field(name="Total Recibido", value=f"{init_data['total_ganado']:,} monedas", inline=False)
                embed_init.add_field(name="XP ganada", value=f"+{init_data['xp_ganada']:,} XP (Nv. {init_data['level']})", inline=True)
                embed_init.add_field(name="Nuevo Saldo", value=f"{init_data['nuevo_saldo']:,} monedas", inline=True)
                if init_data['leveled_up']:
                    embed_init.add_field(name="🎉 ¡Subiste de Nivel!", value=f"Nuevo nivel: **{init_data['level']}** ({init_data['rank']})", inline=False)
                try:
                    await ladron.send(embed=embed_init)
                except Exception:
                    pass

                embed_comp = discord.Embed(
                    title=f"💰 ¡{data['tier_emoji']} {data['tier_nombre']} Exitoso!",
                    description=f"El golpe conjunto contra {victima.mention} ha funcionado.",
                    color=discord.Color.green()
                )
                embed_comp.add_field(name="Monto base", value=f"{data['split_base']:,} monedas", inline=True)
                embed_comp.add_field(name="Bonus por Nivel", value=f"+{comp_data['bonus_loot']:,} monedas", inline=True)
                embed_comp.add_field(name="Total Recibido", value=f"{comp_data['total_ganado']:,} monedas", inline=False)
                embed_comp.add_field(name="XP ganada", value=f"+{comp_data['xp_ganada']:,} XP (Nv. {comp_data['level']})", inline=True)
                embed_comp.add_field(name="Nuevo Saldo", value=f"{comp_data['nuevo_saldo']:,} monedas", inline=True)
                if comp_data['leveled_up']:
                    embed_comp.add_field(name="🎉 ¡Subiste de Nivel!", value=f"Nuevo nivel: **{comp_data['level']}** ({comp_data['rank']})", inline=False)
                try:
                    await complice.send(embed=embed_comp)
                except Exception:
                    pass

                embed_public = discord.Embed(
                    title="🚨 ¡Golpe en Banda Exitoso!",
                    description=f"🥷 {ladron.mention} y {complice.mention} unieron fuerzas para robar a {victima.mention}.\n"
                                f"💸 **Total sustraído:** {data['cantidad_total_robada']:,} monedas.",
                    color=discord.Color.green()
                )
                if interaction.channel and hasattr(interaction.channel, "send"):
                    try:
                        await interaction.channel.send(content=f"🔔 {victima.mention}", embed=embed_public)
                    except Exception as e:
                        logger.warning(f"Error enviando mensaje público de robo en banda: {e}")

            else:  # status == 'fail'
                init_data = data['iniciador']
                comp_data = data['complice']

                embed_init = discord.Embed(
                    title="🚨 ¡Robo en Banda Fallido!",
                    description=f"Fueron descubiertos robando a {victima.mention}.",
                    color=discord.Color.red()
                )
                embed_init.add_field(name="Multa pagada", value=f"{init_data['penalizacion']:,} monedas", inline=True)
                embed_init.add_field(name="XP Perdida", value=f"-{init_data['xp_perdida']:,} XP", inline=True)
                embed_init.add_field(name="Nuevo Saldo", value=f"{init_data['nuevo_saldo']:,} monedas", inline=False)
                try:
                    await ladron.send(embed=embed_init)
                except Exception:
                    pass

                embed_comp = discord.Embed(
                    title="🚨 ¡Robo en Banda Fallido!",
                    description=f"Fueron descubiertos robando a {victima.mention}.",
                    color=discord.Color.red()
                )
                embed_comp.add_field(name="Multa pagada", value=f"{comp_data['penalizacion']:,} monedas", inline=True)
                embed_comp.add_field(name="XP Perdida", value=f"-{comp_data['xp_perdida']:,} XP", inline=True)
                embed_comp.add_field(name="Nuevo Saldo", value=f"{comp_data['nuevo_saldo']:,} monedas", inline=False)
                try:
                    await complice.send(embed=embed_comp)
                except Exception:
                    pass

                embed_public = discord.Embed(
                    title="🚨 ¡Golpe en Banda Frustrado!",
                    description=f"🥷 {ladron.mention} y {complice.mention} intentaron robar a {victima.mention} pero fueron atrapados por las autoridades.",
                    color=discord.Color.red()
                )
                if interaction.channel and hasattr(interaction.channel, "send"):
                    try:
                        await interaction.channel.send(embed=embed_public)
                    except Exception as e:
                        logger.warning(f"Error enviando mensaje público de robo en banda fallido: {e}")

        except Exception as e:
            logger.error("Error en robar_banda", exc_info=True)
            await self._send_safe_interaction(interaction, "❌ Ocurrió un error inesperado al procesar el robo en banda.")


    @app_commands.command(name="robar_banco", description="Ejecuta un intento de robo al Banco Central (Nivel 10+ requerido)")
    @app_commands.describe(
        complice="Opcional: Invitar a un cómplice para cometer el robo en banda"
    )
    @ECONOMY_COOLDOWN
    async def robar_banco_slash(self, interaction: discord.Interaction, complice: discord.Member = None):
        ladron = interaction.user

        # Validaciones de nivel iniciales antes de la invitación (si hay cómplice)
        def _check_db_level(uid):
            with db_cursor() as cursor:
                cursor.execute("SELECT ThiefLevel FROM RoboStats WHERE UserID = %s", (uid,))
                row = cursor.fetchone()
                return row[0] if row else 1

        init_lvl = await asyncio.to_thread(_check_db_level, ladron.id)
        if init_lvl < 10:
            await self._send_safe_interaction(interaction, "❌ Requieres nivel de ladrón 10+ para intentar robar al Banco Central.")
            return

        if complice:
            if complice.bot:
                await self._send_safe_interaction(interaction, "❌ No puedes robar el banco con un bot.")
                return
            if complice.id == ladron.id:
                await self._send_safe_interaction(interaction, "❌ No puedes ser tu propio cómplice.")
                return
            comp_lvl = await asyncio.to_thread(_check_db_level, complice.id)
            if comp_lvl < 10:
                await self._send_safe_interaction(interaction, f"❌ {complice.mention} no tiene nivel de ladrón 10+ requerido.")
                return

            # Responder efímeramente y mandar invitación
            await self._send_safe_interaction(
                interaction,
                f"🕵️ Se ha enviado la invitación a {complice.mention} para robar el Banco Central. Esperando su respuesta..."
            )

            view = RoboBandaInvitationView(initiator=ladron, accomplice=complice, target="Banco Central")
            try:
                msg = await complice.send(
                    f"🥷 **Invitación a un Golpe al Banco Central**\n"
                    f"{ladron.mention} te ha invitado a participar en un golpe al Banco Central.\n"
                    f"Si aceptas, ambos entrarán en un cooldown de 24 horas y el botín se repartirá 50/50.",
                    view=view
                )
                view.message = msg
            except discord.Forbidden:
                await self._send_safe_interaction(
                    interaction,
                    f"❌ No se pudo enviar la invitación a {complice.mention} porque tiene los mensajes privados desactivados."
                )
                return

            await view.wait()
            if not view.accepted:
                await self._send_safe_interaction(
                    interaction,
                    f"❌ El golpe al Banco Central fue cancelado porque {complice.mention} no aceptó la invitación."
                )
                return

        else:
            # Defer la respuesta si no hay cómplice
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=False)
            except Exception:
                pass

        # Ejecutar lógica en BD
        try:
            comp_id = complice.id if complice else None
            comp_name = complice.name if complice else ""
            status, data = await asyncio.to_thread(
                _ejecutar_robo_banco_db,
                ladron.id, comp_id, ladron.name, comp_name
            )

            if status == 'level_low':
                who = "Tú" if data['user'] == 'iniciador' else complice.display_name
                resp = f"❌ {who} no tiene el nivel de ladrón 10+ requerido."
                await self._send_safe_interaction(interaction, resp)
                return

            if status == 'cooldown':
                tr = data['tiempo_restante']
                tiempo_str = _format_timedelta(tr, show_seconds=False)
                who = "Tú" if data['user'] == 'iniciador' else complice.display_name
                resp = f"⏰ {who} debe esperar {tiempo_str} para volver a intentar el asalto al banco."
                await self._send_safe_interaction(interaction, resp)
                return

            if status == 'no_bank_reserves':
                resp = "❌ El Banco no tiene fondos que valga la pena robar ahora mismo."
                await self._send_safe_interaction(interaction, resp)
                return

            # Success / Fail notifications
            if status == 'success':
                if complice:
                    # Enviar DMs privados con detalle
                    init_data = data['iniciador']
                    comp_data = data['complice']

                    embed_init = discord.Embed(
                        title="💰 ¡Golpe al Banco Central Exitoso!",
                        description="¡El gran golpe ha funcionado!",
                        color=discord.Color.green()
                    )
                    embed_init.add_field(name="Tu parte", value=f"{init_data['ganancia']:,} monedas", inline=True)
                    embed_init.add_field(name="XP ganada", value=f"+{init_data['xp_ganada']:,} XP (Nv. {init_data['level']})", inline=True)
                    if init_data['leveled_up']:
                        embed_init.add_field(name="🎉 ¡Subiste de Nivel!", value=f"Nuevo nivel: **{init_data['level']}**", inline=False)
                    try:
                        await ladron.send(embed=embed_init)
                    except Exception:
                        pass

                    embed_comp = discord.Embed(
                        title="💰 ¡Golpe al Banco Central Exitoso!",
                        description="¡El gran golpe ha funcionado!",
                        color=discord.Color.green()
                    )
                    embed_comp.add_field(name="Tu parte", value=f"{comp_data['ganancia']:,} monedas", inline=True)
                    embed_comp.add_field(name="XP ganada", value=f"+{comp_data['xp_ganada']:,} XP (Nv. {comp_data['level']})", inline=True)
                    if comp_data['leveled_up']:
                        embed_comp.add_field(name="🎉 ¡Subiste de Nivel!", value=f"Nuevo nivel: **{comp_data['level']}**", inline=False)
                    try:
                        await complice.send(embed=embed_comp)
                    except Exception:
                        pass

                    # Mensaje público
                    embed_pub = discord.Embed(
                        title="🏛️💰 ¡ASALTO HISTÓRICO AL BANCO CENTRAL!",
                        description=f"🥷 **{ladron.display_name}** y **{complice.display_name}** han asaltado las bóvedas del Banco Central con éxito.\n"
                                    f"💸 **Botín sustraído:** {data['botin_robado']:,} monedas divididas entre ambos.",
                        color=discord.Color.green()
                    )
                    if interaction.channel and hasattr(interaction.channel, "send"):
                        try:
                            await interaction.channel.send(embed=embed_pub)
                        except Exception as e:
                            logger.warning(f"Error enviando mensaje público de asalto al banco: {e}")
                else:
                    # Individual
                    init_data = data['iniciador']
                    embed_pub = discord.Embed(
                        title="🏛️💰 ¡ASALTO AL BANCO CENTRAL EXITOSO!",
                        description=f"🥷 **{ladron.mention}** ha logrado burlar la seguridad del Banco Central.\n"
                                    f"💸 **Botín sustraído:** {init_data['ganancia']:,} monedas.\n"
                                    f"📈 **XP ganada:** +{init_data['xp_ganada']:,} (Nv. {init_data['level']})",
                        color=discord.Color.green()
                    )
                    if init_data['leveled_up']:
                        embed_pub.add_field(name="🎉 ¡Subiste de Nivel!", value=f"Pasaste al nivel **{init_data['level']}**", inline=False)
                    await self._send_safe_interaction(interaction, embed=embed_pub, ephemeral=False)

            else:  # status == 'fail'
                if complice:
                    init_data = data['iniciador']
                    comp_data = data['complice']

                    embed_init = discord.Embed(
                        title="🚨 Asalto al Banco Central Fallido",
                        description="¡Fueron atrapados en la bóveda!",
                        color=discord.Color.red()
                    )
                    embed_init.add_field(name="Multa pagada", value=f"{init_data['penalizacion']:,} monedas", inline=True)
                    embed_init.add_field(name="XP Perdida", value=f"-{init_data['xp_perdida']:,} XP", inline=True)
                    try:
                        await ladron.send(embed=embed_init)
                    except Exception:
                        pass

                    embed_comp = discord.Embed(
                        title="🚨 Asalto al Banco Central Fallido",
                        description="¡Fueron atrapados en la bóveda!",
                        color=discord.Color.red()
                    )
                    embed_comp.add_field(name="Multa pagada", value=f"{comp_data['penalizacion']:,} monedas", inline=True)
                    embed_comp.add_field(name="XP Perdida", value=f"-{comp_data['xp_perdida']:,} XP", inline=True)
                    try:
                        await complice.send(embed=embed_comp)
                    except Exception:
                        pass

                    embed_pub = discord.Embed(
                        title="🏛️🚨 ¡ASALTO FRUSTRADO AL BANCO CENTRAL!",
                        description=f"🥷 **{ladron.display_name}** y **{complice.display_name}** fueron capturados por el equipo Swat táctico del Banco Central.\n"
                                    f"💰 Cada uno ha tenido que pagar una multa de **50,000** monedas, las cuales se reintegraron a las reservas.",
                        color=discord.Color.red()
                    )
                    if interaction.channel and hasattr(interaction.channel, "send"):
                        try:
                            await interaction.channel.send(embed=embed_pub)
                        except Exception as e:
                            logger.warning(f"Error enviando mensaje público de asalto fallido al banco: {e}")
                else:
                    init_data = data['iniciador']
                    embed_pub = discord.Embed(
                        title="🏛️🚨 ¡ASALTO FRUSTRADO AL BANCO CENTRAL!",
                        description=f"🥷 **{ladron.mention}** fue capturado en la bóveda principal del Banco Central.\n"
                                    f"💰 Ha tenido que pagar una multa de **50,000** monedas.",
                        color=discord.Color.red()
                    )
                    await self._send_safe_interaction(interaction, embed=embed_pub, ephemeral=False)

        except Exception as e:
            logger.error("Error en robar_banco", exc_info=True)
            if complice:
                await interaction.followup.send("❌ Ocurrió un error inesperado al procesar el asalto al banco.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Ocurrió un error inesperado al procesar el asalto al banco.")

async def setup(bot):
    await bot.add_cog(Robar(bot))