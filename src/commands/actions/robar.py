import discord
from discord.ext import commands
import discord.app_commands as app_commands
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
    get_protection_hours,
    calcular_robo_dinamico,
    THIEF_MILESTONES,
    ROBO_COOLDOWN_MINUTES,
)
from src.utils.cooldowns import ECONOMY_COOLDOWN

def _get_thief_stats(cursor, user_id, for_update=False):
    lock = " FOR UPDATE" if for_update else ""
    cursor.execute(f"""
        SELECT COALESCE(ThiefLevel, 1), COALESCE(ThiefXP, 0),
               LastRoboTime, COALESCE(RobosExitosos, 0)
        FROM RoboStats WHERE UserID = %s{lock}
    """, (user_id,))
    row = cursor.fetchone()
    if not row:
        return 1, 0, None, 0
    return row[0], row[1], row[2], row[3]

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
        # Inicializar registros de robo si no existen usando ON CONFLICT
        cursor.execute("INSERT INTO RoboStats (UserID) VALUES (%s) ON CONFLICT (UserID) DO NOTHING", (ladron_id,))
        cursor.execute("INSERT INTO RoboStats (UserID) VALUES (%s) ON CONFLICT (UserID) DO NOTHING", (victima_id,))

        thief_level, thief_xp, last_robo, robos_exitosos = _get_thief_stats(cursor, ladron_id, for_update=True)
        cooldown_minutes = get_cooldown_minutes(thief_level)
        
        # Verificar cooldown de robo (reducido por nivel)
        if last_robo and datetime.now() - last_robo < timedelta(minutes=cooldown_minutes):
            tiempo_restante = last_robo + timedelta(minutes=cooldown_minutes) - datetime.now()
            return 'cooldown', {'tiempo_restante': tiempo_restante, 'cooldown_minutes': cooldown_minutes}
        
        # Obtener saldos bloqueando las filas (evita condiciones de carrera)
        # Ordenamos los IDs para prevenir deadlocks si dos usuarios se roban mutuamente al mismo tiempo
        id_1, id_2 = min(ladron_id, victima_id), max(ladron_id, victima_id)
        cursor.execute("SELECT UserID, Balance FROM Users WHERE UserID IN (%s, %s) FOR UPDATE", (id_1, id_2))
        rows = cursor.fetchall()
        
        saldo_ladron = 0
        saldo_victima = 0
        for uid, bal in rows:
            if uid == ladron_id:
                saldo_ladron = bal
            elif uid == victima_id:
                saldo_victima = bal
        
        # Verificar si la víctima tiene saldo suficiente (al menos 1000)
        if saldo_victima < 1000:
            return 'no_money', {}
        
        # Verificar protección de la víctima (ESCALONADA según su saldo)
        protection_hours = get_protection_hours(saldo_victima)
        cursor.execute("SELECT LastRobadoTime FROM RoboStats WHERE UserID = %s", (victima_id,))
        result = cursor.fetchone()
        last_robado = result[0] if result else None
        
        if last_robado and datetime.now() - last_robado < timedelta(hours=protection_hours):
            tiempo_restante = last_robado + timedelta(hours=protection_hours) - datetime.now()
            return 'protection', {'tiempo_restante': tiempo_restante, 'protection_hours': protection_hours}
        
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
        
        # Aplicar dificultad dinámica
        difficulty_modifier, _ = DynamicDifficulty.calculate_dynamic_difficulty(
            ladron_id, cantidad_a_robar, 'robo'
        )
        prob_exito -= int(difficulty_modifier * 30)
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
                'protection_hours': protection_hours,
                'robo_params': robo_params,
                'prob_exito_final': int(prob_exito),
            }
        else:
            # Penalización dinámica basada en el tier
            penalizacion = int(cantidad_a_robar * (penalizacion_pct / 100))
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

            cursor.execute("""
                UPDATE RoboStats SET 
                RobosFallidos = COALESCE(RobosFallidos, 0) + 1,
                TotalPerdido = COALESCE(TotalPerdido, 0) + %s,
                ThiefLevel = %s,
                ThiefXP = %s
                WHERE UserID = %s
            """, (penalizacion, xp_result["level"], xp_result["xp"], ladron_id))
            
            # Registrar en log
            cursor.execute("""
                INSERT INTO RoboLog (LadronID, VictimaID, CantidadRobada, Exitoso)
                VALUES (%s, %s, %s, FALSE)
            """, (ladron_id, victima_id, 0))
            
            return 'fail', {
                'penalizacion': penalizacion,
                'nuevo_saldo_ladron': nuevo_saldo_ladron,
                'xp_perdida': xp_perdida,
                'thief_level': xp_result["level"],
                'thief_xp': xp_result["xp"],
                'xp_for_next': xp_result["xp_for_next"],
                'leveled_down': xp_result["leveled_down"],
                'previous_level': xp_result["previous_level"],
                'rank': xp_result["rank"],
                'cooldown_minutes': get_cooldown_minutes(xp_result["level"]),
                'robo_params': robo_params,
                'prob_exito_final': int(prob_exito),
            }

class Robar(commands.Cog):
    """Cog para el comando de robar dinero a otros usuarios."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="perfil_ladron", description="Muestra tu nivel, rango y bonificaciones como ladrón.")
    async def perfil_ladron_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

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
            title=f"🥷 Perfil de Ladrón — {interaction.user.display_name}",
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

        await interaction.followup.send(embed=embed, ephemeral=True)

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
            await ctx_or_interaction.response.defer()
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
                await ctx_or_interaction.followup.send(respuesta, ephemeral=True)
            else:
                await ctx_or_interaction.send(respuesta)
            return
            
        if ladron_id == victima_id:
            respuesta = "❌ No puedes robarte a ti mismo."
            if is_slash:
                await ctx_or_interaction.followup.send(respuesta, ephemeral=True)
            else:
                await ctx_or_interaction.send(respuesta)
            return
            
        try:
            # Enviar mensaje inicial
            if is_slash:
                msg = await ctx_or_interaction.followup.send("🕵️ Analizando al objetivo... calculando el plan...", ephemeral=False)
            else:
                msg = await ctx_or_interaction.send("🕵️ Analizando al objetivo... calculando el plan...")
            
            # Ejecutar validaciones y lógica de robo en base de datos en un hilo secundario
            status, data = await asyncio.to_thread(
                _ejecutar_robo_db, ladron_id, victima_id, ladron_name, victima_name
            )
            
            if status == 'cooldown':
                tr = data['tiempo_restante']
                minutos = tr.seconds // 60
                segundos = tr.seconds % 60
                await msg.edit(content=f"⏰ Debes esperar {minutos}m {segundos}s para intentar robar nuevamente.", embed=None)
                return
                
            if status == 'protection':
                tr = data['tiempo_restante']
                horas = tr.seconds // 3600
                minutos = (tr.seconds % 3600) // 60
                prot_h = data['protection_hours']
                await msg.edit(content=f"🛡️ {victima.mention} tiene protección por {horas}h {minutos}m más (protección de {prot_h:.0f}h por su saldo).", embed=None)
                return
                
            if status == 'no_money':
                await msg.edit(content=f"❌ {victima.mention} no tiene suficiente dinero para robarle (mínimo 1,000 monedas).", embed=None)
                return
            
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
            embed_preparacion.add_field(name="Preparándose", value="Reconociendo el terreno...", inline=False)
            await msg.edit(content=None, embed=embed_preparacion)
            
            await asyncio.sleep(2)
            embed_preparacion.add_field(name="En Posición", value="Calculando rutas de escape...", inline=False)
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
                embed_exito.set_footer(text=f"{victima_name} tiene protección {data['protection_hours']:.0f}h · Próximo robo en {data['cooldown_minutes']:.0f} min")
                await msg.edit(embed=embed_exito)
                
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
                embed_fracaso.add_field(name="XP Perdida", value=f"-{data['xp_perdida']:,} XP", inline=True)
                embed_fracaso.add_field(
                    name="Tu Rango",
                    value=f"**{data['rank']}** (Nv. {data['thief_level']})",
                    inline=True
                )
                if data.get('leveled_down'):
                    embed_fracaso.add_field(
                        name="📉 Bajaste de Nivel",
                        value=f"Caíste del nivel **{data['previous_level']}** al **{data['thief_level']}**.\nNuevo rango: **{data['rank']}**",
                        inline=False
                    )
                elif data.get('xp_for_next', 0) > 0:
                    bar = format_progress_bar(data['thief_xp'], data['xp_for_next'])
                    embed_fracaso.add_field(
                        name="Progreso",
                        value=f"`{bar}` {data['thief_xp']:,}/{data['xp_for_next']:,} XP",
                        inline=False
                    )
                embed_fracaso.add_field(name="Nuevo Saldo", value=f"{data['nuevo_saldo_ladron']:,} monedas", inline=True)
                embed_fracaso.set_footer(text=f"Próximo robo en {data['cooldown_minutes']:.0f} min · Usa /perfil_ladron para ver bonificaciones")
                await msg.edit(embed=embed_fracaso)
                
        except Exception as e:
            print(f"Error en comando robar: {e}")
            respuesta = "❌ Ocurrió un error al procesar el robo."
            if is_slash:
                await ctx_or_interaction.followup.send(respuesta, ephemeral=True)
            else:
                await ctx_or_interaction.send(respuesta)
            raise

async def setup(bot):
    await bot.add_cog(Robar(bot))