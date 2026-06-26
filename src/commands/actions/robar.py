import discord
from discord.ext import commands
import discord.app_commands as app_commands
import random
import asyncio
from datetime import datetime, timedelta
from src.db import get_balance, ensure_user, db_cursor
from src.utils.dynamic_difficulty import DynamicDifficulty

def _ejecutar_robo_db(ladron_id, victima_id, porcentaje, ladron_name, victima_name):
    """
    Realiza todas las validaciones de negocio y transacciones de base de datos para el robo de forma atómica en PostgreSQL.
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
        
        # Verificar cooldown de robo (15 minutos entre robos)
        cursor.execute("SELECT LastRoboTime FROM RoboStats WHERE UserID = %s", (ladron_id,))
        result = cursor.fetchone()
        last_robo = result[0] if result else None
        
        if last_robo and datetime.now() - last_robo < timedelta(minutes=15):
            tiempo_restante = last_robo + timedelta(minutes=15) - datetime.now()
            return 'cooldown', {'tiempo_restante': tiempo_restante}
        
        # Verificar protección de la víctima (3 horas)
        cursor.execute("SELECT LastRobadoTime FROM RoboStats WHERE UserID = %s", (victima_id,))
        result = cursor.fetchone()
        last_robado = result[0] if result else None
        
        if last_robado and datetime.now() - last_robado < timedelta(hours=3):
            tiempo_restante = last_robado + timedelta(hours=3) - datetime.now()
            return 'protection', {'tiempo_restante': tiempo_restante}
        
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
        
        # Calcular cantidad a robar
        cantidad_a_robar = int(saldo_victima * (porcentaje / 100))
        cantidad_a_robar = min(cantidad_a_robar, int(saldo_victima * 0.25))
        
        # Calcular probabilidad de éxito
        prob_exito = 60
        prob_exito -= (porcentaje - 5) * 2
        
        if saldo_victima > saldo_ladron * 2:
            prob_exito -= 15
        elif saldo_victima > saldo_ladron:
            prob_exito -= 5
        
        # Historial de robos exitosos
        cursor.execute("SELECT RobosExitosos FROM RoboStats WHERE UserID = %s", (ladron_id,))
        result_stats = cursor.fetchone()
        robos_exitosos = result_stats[0] if result_stats and result_stats[0] is not None else 0
        
        if robos_exitosos > 20:
            prob_exito += 15
        elif robos_exitosos > 10:
            prob_exito += 10
        elif robos_exitosos > 5:
            prob_exito += 5
        
        # Aplicar dificultad dinámica
        difficulty_modifier, _ = DynamicDifficulty.calculate_dynamic_difficulty(
            ladron_id, cantidad_a_robar, 'robo'
        )
        prob_exito -= int(difficulty_modifier * 50)
        prob_exito = max(10, min(90, prob_exito))
        
        # Registrar intento de robo (actualizar cooldown)
        cursor.execute("UPDATE RoboStats SET LastRoboTime = CURRENT_TIMESTAMP WHERE UserID = %s", (ladron_id,))
        
        # Determinar resultado del robo
        exito = random.randint(1, 100) <= prob_exito
        
        if exito:
            # Actualizar balances relativos
            cursor.execute("UPDATE Users SET Balance = Balance - %s WHERE UserID = %s RETURNING Balance", (cantidad_a_robar, victima_id))
            nuevo_saldo_victima = cursor.fetchone()[0]
            
            cursor.execute("UPDATE Users SET Balance = Balance + %s WHERE UserID = %s RETURNING Balance", (cantidad_a_robar, ladron_id))
            nuevo_saldo_ladron = cursor.fetchone()[0]
            
            # Registrar transacciones
            cursor.execute("""
                INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            """, (ladron_id, cantidad_a_robar, f"Robo: éxito vs {victima_name}"))
            cursor.execute("""
                INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            """, (victima_id, -cantidad_a_robar, f"Robado por {ladron_name}"))
            
            # Actualizar estadísticas de robo
            cursor.execute("""
                UPDATE RoboStats SET 
                RobosExitosos = COALESCE(RobosExitosos, 0) + 1,
                TotalRobado = COALESCE(TotalRobado, 0) + %s
                WHERE UserID = %s
            """, (cantidad_a_robar, ladron_id))
            
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
                'nuevo_saldo_ladron': nuevo_saldo_ladron,
                'nuevo_saldo_victima': nuevo_saldo_victima
            }
        else:
            # Calcular penalización (10-30% de lo que intentó robar)
            penalizacion = int(cantidad_a_robar * (random.randint(10, 30) / 100))
            penalizacion = min(penalizacion, saldo_ladron)
            
            nuevo_saldo_ladron = saldo_ladron - penalizacion
            if penalizacion > 0:
                cursor.execute("UPDATE Users SET Balance = %s WHERE UserID = %s", (nuevo_saldo_ladron, ladron_id))
                cursor.execute("""
                    INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                """, (ladron_id, -penalizacion, "Multa por intento de robo"))
            
            # Actualizar estadísticas de robo fallido
            cursor.execute("""
                UPDATE RoboStats SET 
                RobosFallidos = COALESCE(RobosFallidos, 0) + 1,
                TotalPerdido = COALESCE(TotalPerdido, 0) + %s
                WHERE UserID = %s
            """, (penalizacion, ladron_id))
            
            # Registrar en log
            cursor.execute("""
                INSERT INTO RoboLog (LadronID, VictimaID, CantidadRobada, Exitoso)
                VALUES (%s, %s, %s, FALSE)
            """, (ladron_id, victima_id, 0))
            
            return 'fail', {
                'penalizacion': penalizacion,
                'nuevo_saldo_ladron': nuevo_saldo_ladron
            }

class Robar(commands.Cog):
    """Cog para el comando de robar dinero a otros usuarios."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="robar", description="Intenta robar dinero a otro usuario")
    @app_commands.describe(
        victima="Usuario al que intentarás robar",
        porcentaje="Porcentaje de dinero a intentar robar (1-25%)"
    )
    async def robar_slash(self, interaction: discord.Interaction, victima: discord.Member, porcentaje: int = 10):
        await self._robar_logica(interaction, victima, porcentaje, is_slash=True)
    
    @commands.command(name="robar", help="Intenta robar dinero a otro usuario. Uso: !robar @usuario [porcentaje]")
    async def robar(self, ctx, victima: discord.Member, porcentaje: int = 10):
        await self._robar_logica(ctx, victima, is_slash=False, porcentaje=porcentaje)
    
    async def _robar_logica(self, ctx_or_interaction, victima: discord.Member, porcentaje: int = 10, is_slash: bool = False):
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
        
        if porcentaje < 1 or porcentaje > 25:
            respuesta = "❌ El porcentaje debe estar entre 1% y 25%."
            if is_slash:
                await ctx_or_interaction.followup.send(respuesta, ephemeral=True)
            else:
                await ctx_or_interaction.send(respuesta)
            return
            
        try:
            # Enviar mensaje inicial
            if is_slash:
                msg = await ctx_or_interaction.followup.send("🕵️ Intentando robar... espera el resultado...", ephemeral=False)
            else:
                msg = await ctx_or_interaction.send("🕵️ Intentando robar... espera el resultado...")
            
            # Ejecutar validaciones y lógica de robo en base de datos en un hilo secundario
            status, data = await asyncio.to_thread(
                _ejecutar_robo_db, ladron_id, victima_id, porcentaje, ladron_name, victima_name
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
                await msg.edit(content=f"🛡️ {victima.mention} tiene protección por {horas}h {minutos}m más.", embed=None)
                return
                
            if status == 'no_money':
                await msg.edit(content=f"❌ {victima.mention} no tiene suficiente dinero para robarle (mínimo 1,000 monedas).", embed=None)
                return
            
            # Mostrar preparación animada
            embed_preparacion = discord.Embed(
                title="🕵️ Intento de Robo",
                description=f"{ladron.mention} intenta robar a {victima.mention}...",
                color=discord.Color.gold()
            )
            embed_preparacion.add_field(name="Objetivo", value=f"Robar el {porcentaje}% del dinero de {victima.mention}", inline=False)
            embed_preparacion.add_field(name="Preparándose", value="Reconociendo el terreno...", inline=False)
            await msg.edit(content=None, embed=embed_preparacion)
            
            await asyncio.sleep(2)
            embed_preparacion.add_field(name="En Posición", value="Calculando rutas de escape...", inline=False)
            await msg.edit(embed=embed_preparacion)
            
            await asyncio.sleep(2)
            
            if status == 'success':
                embed_exito = discord.Embed(
                    title="💰 ¡Robo Exitoso!",
                    description=f"{ladron.mention} ha robado exitosamente a {victima.mention}",
                    color=discord.Color.green()
                )
                embed_exito.add_field(name="Cantidad Robada", value=f"{data['cantidad_a_robar']:,} monedas", inline=False)
                embed_exito.add_field(name="Nuevo Saldo (Ladrón)", value=f"{data['nuevo_saldo_ladron']:,} monedas", inline=True)
                embed_exito.add_field(name="Nuevo Saldo (Víctima)", value=f"{data['nuevo_saldo_victima']:,} monedas", inline=True)
                embed_exito.set_footer(text=f"{victima_name} tiene protección contra robos durante 3 horas.")
                await msg.edit(embed=embed_exito)
                
            else:  # status == 'fail'
                embed_fracaso = discord.Embed(
                    title="🚨 ¡Robo Fallido!",
                    description=f"{ladron.mention} fue descubierto intentando robar a {victima.mention}",
                    color=discord.Color.red()
                )
                embed_fracaso.add_field(name="Multa por Intento", value=f"{data['penalizacion']:,} monedas", inline=False)
                embed_fracaso.add_field(name="Nuevo Saldo", value=f"{data['nuevo_saldo_ladron']:,} monedas", inline=True)
                embed_fracaso.set_footer(text="Debes esperar 15 minutos para intentar robar nuevamente.")
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