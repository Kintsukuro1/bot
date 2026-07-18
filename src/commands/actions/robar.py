import discord
from discord.ext import commands
import discord.app_commands as app_commands
import logging

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
        # Ordenamos los IDs para prevenir deadlocks si dos usuarios se roban mutuamente al mismo tiempo
        id_1, id_2 = min(ladron_id, victima_id), max(ladron_id, victima_id)
        cursor.execute("SELECT UserID, Balance FROM Users WHERE UserID IN (%s, %s) FOR UPDATE", (id_1, id_2))
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
            
            cooldown_efectivo = cooldown_actual * FAIL_COOLDOWN_FACTOR
            
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

    async def _perfil_ladron_logica(self, ctx_or_interaction):
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.defer(ephemeral=True)
            user = ctx_or_interaction.user
            send_func = ctx_or_interaction.followup.send
            send_kwargs = {"ephemeral": True}
        else:
            user = ctx_or_interaction.author
            send_func = ctx_or_interaction.send
            send_kwargs = {}
        
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
        if is_slash:
            ladron = ctx_or_interaction.user
        else:
            ladron = ctx_or_interaction.author
        
        ladron_id = ladron.id
        ladron_name = ladron.name
        victima_id = victima.id
        victima_name = victima.name
        
        # Validaciones iniciales
        if victima.bot:
            respuesta = "❌ No puedes robar a un bot."
            if is_slash:
                await ctx_or_interaction.response.send_message(respuesta, ephemeral=True)
            else:
                await ctx_or_interaction.send(respuesta)
            return
            
        if ladron_id == victima_id:
            respuesta = "❌ No puedes robarte a ti mismo."
            if is_slash:
                await ctx_or_interaction.response.send_message(respuesta, ephemeral=True)
            else:
                await ctx_or_interaction.send(respuesta)
            return
            
        try:
            # Ejecutar validaciones y lógica de robo en base de datos en un hilo secundario PRIMERO
            status, data = await asyncio.to_thread(
                _ejecutar_robo_db, ladron_id, victima_id, ladron_name, victima_name
            )
            
            if status == 'cooldown':
                tr = data['tiempo_restante']
                tiempo_str = _format_timedelta(tr, show_seconds=True)
                respuesta = f"⏰ Debes esperar {tiempo_str} para intentar robar nuevamente."
                if is_slash:
                    await ctx_or_interaction.response.send_message(respuesta, ephemeral=True)
                else:
                    await ctx_or_interaction.send(respuesta)
                return
                
            if status == 'shield_active':
                tr = data['tiempo_restante']
                tiempo_str = _format_timedelta(tr, show_seconds=False)
                respuesta = f"🛡️🌟 {victima.mention} tiene un **Escudo Total** activo. Es inmune a robos por {tiempo_str} más."
                if is_slash:
                    await ctx_or_interaction.response.send_message(respuesta, ephemeral=True)
                else:
                    await ctx_or_interaction.send(respuesta)
                return

            if status == 'protection':
                tr = data['tiempo_restante']
                tiempo_str = _format_timedelta(tr, show_seconds=False)
                prot_m = data['protection_minutes']
                respuesta = f"🛡️ {victima.mention} tiene protección por {tiempo_str} más (protección de {prot_m} min tras robo)."
                if is_slash:
                    await ctx_or_interaction.response.send_message(respuesta, ephemeral=True)
                else:
                    await ctx_or_interaction.send(respuesta)
                return
                
            if status == 'no_money':
                respuesta = f"❌ {victima.mention} no tiene suficiente dinero para robarle (mínimo {VICTIMA_MIN_SALDO:,} monedas)."
                if is_slash:
                    await ctx_or_interaction.response.send_message(respuesta, ephemeral=True)
                else:
                    await ctx_or_interaction.send(respuesta)
                return
            
            # Si llegamos aquí, el robo fue success o fail y la base de datos ya se actualizó.
            # Procedemos a enviar el mensaje público de preparación y la animación.
            if is_slash:
                await ctx_or_interaction.response.defer(ephemeral=False)
                msg = await ctx_or_interaction.followup.send("🕵️ Analizando al objetivo... calculando el plan...", ephemeral=False)
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
            await msg.edit(content=None, embed=embed_preparacion)
            
            await asyncio.sleep(2)
            embed_preparacion.set_field_at(2, name="🔍 Estado", value="🏃 Calculando rutas de escape...", inline=False)
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
            raise

async def setup(bot):
    await bot.add_cog(Robar(bot))