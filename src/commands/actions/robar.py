import discord
from discord.ext import commands
import discord.app_commands as app_commands
import random
import time
import asyncio
from datetime import datetime, timedelta
import sys
import os

# Importar configuraciones y conexión a base de datos
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db import get_balance, set_balance, conn_str, ensure_user
from utils.dynamic_difficulty import DynamicDifficulty
import pyodbc

class Robar(commands.Cog):
    """Cog para el comando de robar dinero a otros usuarios."""
    
    def __init__(self, bot):
        self.bot = bot
        self._init_robo_tables()
    
    def _init_robo_tables(self):
        """Inicializa las tablas necesarias para el sistema de robo."""
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        try:
            # Tabla para registrar robos y protecciones
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='RoboStats' AND xtype='U')
                CREATE TABLE RoboStats (
                    UserID BIGINT PRIMARY KEY,
                    LastRoboTime DATETIME2,
                    LastRobadoTime DATETIME2,
                    RobosExitosos INT DEFAULT 0,
                    RobosFallidos INT DEFAULT 0,
                    TotalRobado BIGINT DEFAULT 0,
                    TotalPerdido BIGINT DEFAULT 0,
                    ProteccionActiva BIT DEFAULT 0
                )
            """)
            
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='RoboLog' AND xtype='U')
                CREATE TABLE RoboLog (
                    LogID INT IDENTITY(1,1) PRIMARY KEY,
                    LadronID BIGINT NOT NULL,
                    VictimaID BIGINT NOT NULL,
                    CantidadRobada BIGINT NOT NULL,
                    Exitoso BIT NOT NULL,
                    Timestamp DATETIME2 DEFAULT GETDATE()
                )
            """)
            
            conn.commit()
        except Exception as e:
            print(f"Error al crear tablas de robo: {e}")
        finally:
            cursor.close()
            conn.close()
    
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
        # Obtener información del ladrón y la víctima
        if is_slash:
            ladron = ctx_or_interaction.user
            ladron_id = ladron.id
            ladron_name = ladron.name
        else:
            ladron = ctx_or_interaction.author
            ladron_id = ladron.id
            ladron_name = ladron.name
        
        victima_id = victima.id
        victima_name = victima.name
        
        # Asegurar que ambos usuarios existan en la base de datos
        ensure_user(ladron_id, ladron_name)
        ensure_user(victima_id, victima_name)
        
        # Validaciones iniciales
        # No puede robarse a sí mismo
        if ladron_id == victima_id:
            respuesta = "❌ No puedes robarte a ti mismo."
            if is_slash:
                await ctx_or_interaction.response.send_message(respuesta, ephemeral=True)
            else:
                await ctx_or_interaction.send(respuesta)
            return
        
        # Validar porcentaje
        if porcentaje < 1 or porcentaje > 25:
            respuesta = "❌ El porcentaje debe estar entre 1% y 25%."
            if is_slash:
                await ctx_or_interaction.response.send_message(respuesta, ephemeral=True)
            else:
                await ctx_or_interaction.send(respuesta)
            return
        
        # Verificar tiempos de enfriamiento y protecciones
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        try:
            # Inicializar registro de robo si no existe
            cursor.execute("IF NOT EXISTS (SELECT 1 FROM RoboStats WHERE UserID = ?) INSERT INTO RoboStats (UserID) VALUES (?)", 
                          (ladron_id, ladron_id))
            cursor.execute("IF NOT EXISTS (SELECT 1 FROM RoboStats WHERE UserID = ?) INSERT INTO RoboStats (UserID) VALUES (?)", 
                          (victima_id, victima_id))
            
            # Verificar cooldown de robo (15 minutos entre robos)
            cursor.execute("SELECT LastRoboTime FROM RoboStats WHERE UserID = ?", (ladron_id,))
            result = cursor.fetchone()
            last_robo = result[0] if result else None
            
            if last_robo and datetime.now() - last_robo < timedelta(minutes=15):
                tiempo_restante = last_robo + timedelta(minutes=15) - datetime.now()
                minutos = tiempo_restante.seconds // 60
                segundos = tiempo_restante.seconds % 60
                
                respuesta = f"⏰ Debes esperar {minutos}m {segundos}s para intentar robar nuevamente."
                if is_slash:
                    await ctx_or_interaction.response.send_message(respuesta, ephemeral=True)
                else:
                    await ctx_or_interaction.send(respuesta)
                return
            
            # Verificar protección de la víctima (3 horas)
            cursor.execute("SELECT LastRobadoTime FROM RoboStats WHERE UserID = ?", (victima_id,))
            result = cursor.fetchone()
            last_robado = result[0] if result else None
            
            if last_robado and datetime.now() - last_robado < timedelta(hours=3):
                tiempo_restante = last_robado + timedelta(hours=3) - datetime.now()
                horas = tiempo_restante.seconds // 3600
                minutos = (tiempo_restante.seconds % 3600) // 60
                
                respuesta = f"🛡️ {victima.mention} tiene protección por {horas}h {minutos}m más."
                if is_slash:
                    await ctx_or_interaction.response.send_message(respuesta, ephemeral=True)
                else:
                    await ctx_or_interaction.send(respuesta)
                return
            
            # Obtener saldos
            saldo_ladron = get_balance(ladron_id)
            saldo_victima = get_balance(victima_id)
            
            # Verificar si la víctima tiene saldo suficiente (al menos 1000)
            if saldo_victima < 1000:
                respuesta = f"❌ {victima.mention} no tiene suficiente dinero para robarle."
                if is_slash:
                    await ctx_or_interaction.response.send_message(respuesta, ephemeral=True)
                else:
                    await ctx_or_interaction.send(respuesta)
                return
            
            # Calcular cantidad a robar
            cantidad_a_robar = int(saldo_victima * (porcentaje / 100))
            
            # Límite máximo de robo (25% del saldo de la víctima)
            cantidad_a_robar = min(cantidad_a_robar, int(saldo_victima * 0.25))
            
            # Calcular probabilidad de éxito
            # Base: 60% de éxito
            prob_exito = 60
            
            # Factores que afectan la probabilidad:
            # 1. Porcentaje robado (mayor porcentaje = menor probabilidad)
            prob_exito -= (porcentaje - 5) * 2  # -2% por cada 1% sobre 5%
            
            # 2. Diferencia de saldo (robar a alguien con más dinero es más difícil)
            if saldo_victima > saldo_ladron * 2:
                prob_exito -= 15
            elif saldo_victima > saldo_ladron:
                prob_exito -= 5
            
            # 3. Historial de robos exitosos (más éxitos = más habilidad)
            cursor.execute("SELECT RobosExitosos FROM RoboStats WHERE UserID = ?", (ladron_id,))
            result = cursor.fetchone()
            robos_exitosos = result[0] if result and result[0] is not None else 0
            
            if robos_exitosos > 20:
                prob_exito += 15
            elif robos_exitosos > 10:
                prob_exito += 10
            elif robos_exitosos > 5:
                prob_exito += 5
            
            # 4. Aplicar dificultad dinámica
            difficulty_modifier, _ = DynamicDifficulty.calculate_dynamic_difficulty(
                ladron_id, cantidad_a_robar, 'robo'
            )
            
            # Convertir el modificador de dificultad a un ajuste de porcentaje (-25% a +25%)
            prob_exito -= int(difficulty_modifier * 50)
            
            # Limitar probabilidad entre 10% y 90%
            prob_exito = max(10, min(90, prob_exito))
            
            # Preparar mensaje inicial
            if is_slash:
                await ctx_or_interaction.response.send_message("🕵️ Intentando robar... espera el resultado...", ephemeral=False)
                msg = await ctx_or_interaction.original_response()
            else:
                msg = await ctx_or_interaction.send("🕵️ Intentando robar... espera el resultado...")
            
            # Crear embed de preparación
            embed_preparacion = discord.Embed(
                title="🕵️ Intento de Robo",
                description=f"{ladron.mention} intenta robar a {victima.mention}...",
                color=discord.Color.gold()
            )
            embed_preparacion.add_field(name="Objetivo", value=f"Robar el {porcentaje}% del dinero de {victima.mention}", inline=False)
            embed_preparacion.add_field(name="Preparándose", value="Reconociendo el terreno...", inline=False)
            await msg.edit(content=None, embed=embed_preparacion)
            
            # Esperar para crear tensión
            await asyncio.sleep(2)
            
            # Actualizar embed con más detalles
            embed_preparacion.add_field(name="En Posición", value="Calculando rutas de escape...", inline=False)
            await msg.edit(embed=embed_preparacion)
            
            # Más espera
            await asyncio.sleep(2)
            
            # Determinar resultado del robo
            exito = random.randint(1, 100) <= prob_exito
            
            # Registrar intento de robo
            cursor.execute("UPDATE RoboStats SET LastRoboTime = GETDATE() WHERE UserID = ?", (ladron_id,))
            
            if exito:
                # Robo exitoso
                # Actualizar saldos
                set_balance(victima_id, get_balance(victima_id) - cantidad_a_robar)
                set_balance(ladron_id, get_balance(ladron_id) + cantidad_a_robar)
                
                # Actualizar estadísticas
                cursor.execute("""
                    UPDATE RoboStats SET 
                    RobosExitosos = ISNULL(RobosExitosos, 0) + 1,
                    TotalRobado = ISNULL(TotalRobado, 0) + ?,
                    LastRoboTime = GETDATE()
                    WHERE UserID = ?
                """, (cantidad_a_robar, ladron_id))
                
                cursor.execute("""
                    UPDATE RoboStats SET 
                    TotalPerdido = ISNULL(TotalPerdido, 0) + ?,
                    LastRobadoTime = GETDATE()
                    WHERE UserID = ?
                """, (cantidad_a_robar, victima_id))
                
                # Registrar en log
                cursor.execute("""
                    INSERT INTO RoboLog (LadronID, VictimaID, CantidadRobada, Exitoso)
                    VALUES (?, ?, ?, 1)
                """, (ladron_id, victima_id, cantidad_a_robar))
                
                # Crear embed de éxito
                embed_exito = discord.Embed(
                    title="💰 ¡Robo Exitoso!",
                    description=f"{ladron.mention} ha robado exitosamente a {victima.mention}",
                    color=discord.Color.green()
                )
                embed_exito.add_field(name="Cantidad Robada", value=f"{cantidad_a_robar:,} monedas", inline=False)
                embed_exito.add_field(name="Nuevo Saldo (Ladrón)", value=f"{get_balance(ladron_id):,} monedas", inline=True)
                embed_exito.add_field(name="Nuevo Saldo (Víctima)", value=f"{get_balance(victima_id):,} monedas", inline=True)
                embed_exito.set_footer(text=f"{victima_name} tiene protección contra robos durante 3 horas.")
                
                await msg.edit(content=None, embed=embed_exito)
                
            else:
                # Robo fallido
                # Calcular penalización (10-30% de lo que intentó robar)
                penalizacion = int(cantidad_a_robar * (random.randint(10, 30) / 100))
                penalizacion = min(penalizacion, saldo_ladron)  # No puede perder más de lo que tiene
                
                if penalizacion > 0:
                    set_balance(ladron_id, get_balance(ladron_id) - penalizacion)
                
                # Actualizar estadísticas
                cursor.execute("""
                    UPDATE RoboStats SET 
                    RobosFallidos = ISNULL(RobosFallidos, 0) + 1,
                    TotalPerdido = ISNULL(TotalPerdido, 0) + ?,
                    LastRoboTime = GETDATE()
                    WHERE UserID = ?
                """, (penalizacion, ladron_id))
                
                # Registrar en log
                cursor.execute("""
                    INSERT INTO RoboLog (LadronID, VictimaID, CantidadRobada, Exitoso)
                    VALUES (?, ?, ?, 0)
                """, (ladron_id, victima_id, 0))
                
                # Crear embed de fracaso
                embed_fracaso = discord.Embed(
                    title="🚨 ¡Robo Fallido!",
                    description=f"{ladron.mention} fue descubierto intentando robar a {victima.mention}",
                    color=discord.Color.red()
                )
                embed_fracaso.add_field(name="Multa por Intento", value=f"{penalizacion:,} monedas", inline=False)
                embed_fracaso.add_field(name="Nuevo Saldo", value=f"{get_balance(ladron_id):,} monedas", inline=True)
                embed_fracaso.set_footer(text="Debes esperar 15 minutos para intentar robar nuevamente.")
                
                await msg.edit(content=None, embed=embed_fracaso)
                
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            print(f"Error en comando robar: {e}")
            respuesta = "❌ Ocurrió un error al procesar el robo."
            
            if is_slash:
                if not ctx_or_interaction.response.is_done():
                    await ctx_or_interaction.response.send_message(respuesta, ephemeral=True)
            else:
                await ctx_or_interaction.send(respuesta)
        finally:
            cursor.close()
            conn.close()


async def setup(bot):
    await bot.add_cog(Robar(bot))