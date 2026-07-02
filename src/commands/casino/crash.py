import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from src.db import get_balance, set_balance, deduct_balance, add_balance, ensure_user, registrar_transaccion, record_game_result
from src.commands.economy.pets import process_post_game_events
from src.utils.dynamic_difficulty import DynamicDifficulty
from src.utils.cooldowns import CASINO_COOLDOWN

CRASH_TICKET_MAX_BET = 5000
CRASH_TICKET_ITEM_ID = 6

class Crash(commands.Cog):
    """Cog para el juego Crash."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="crash", description="Juega Crash: apuesta y retírate antes de que el multiplicador explote!")
    @app_commands.describe(apuesta="Cantidad de monedas a apostar")
    @CASINO_COOLDOWN
    async def crash_slash(self, interaction: discord.Interaction, apuesta: int):
        await self._crash_game(interaction, apuesta, is_slash=True)

    @commands.command(name="crash", help="Juega Crash: apuesta y retírate antes de que el multiplicador explote! Uso: !crash <apuesta>")
    async def crash(self, ctx, apuesta: int):
        await self._crash_game(ctx, apuesta, is_slash=False)

    async def _crash_game(self, ctx_or_interaction, apuesta: int, is_slash: bool = False):
        if is_slash:
            await ctx_or_interaction.response.defer()
            user = ctx_or_interaction.user
            user_id = user.id
            user_name = user.name
        else:
            user = ctx_or_interaction.author
            user_id = user.id
            user_name = user.name
            
        await asyncio.to_thread(ensure_user, user_id, user_name)
        if apuesta <= 0:
            error_msg = "❌ La apuesta debe ser mayor a 0."
            if is_slash:
                await ctx_or_interaction.followup.send(error_msg, ephemeral=True)
            else:
                await ctx_or_interaction.send(error_msg)
            return

        success, saldo = await asyncio.to_thread(deduct_balance, user_id, apuesta)
        if not success:
            error_msg = f"❌ No tienes suficiente saldo para esa apuesta."
            if is_slash:
                await ctx_or_interaction.followup.send(error_msg, ephemeral=True)
            else:
                await ctx_or_interaction.send(error_msg)
            return
        # Calcular dificultad dinámica
        difficulty_modifier, difficulty_explanation = await asyncio.to_thread(
            DynamicDifficulty.calculate_dynamic_difficulty, user_id, apuesta, 'crash'
        )
        
        # Determinar la base del crash point usando una distribución de probabilidad realista
        # House edge base del 4% (ventaja de la casa)
        base_edge = 0.04
        # Ajustar la ventaja de la casa según la dificultad del jugador (-0.5 a 0.5)
        edge = base_edge + (difficulty_modifier * 0.16)
        edge = max(0.01, min(0.15, edge))
        
        U = random.random()
        # Evitar división por cero
        U_adj = min(U, 0.99)
        
        # Algoritmo clásico y justo de Crash: M = (1 - edge) / (1 - U)
        val = (1.0 - edge) / (1.0 - U_adj)
        
        # Quitar la probabilidad de que explote en 1 (choque instantáneo)
        if val <= 1.0:
            val = random.uniform(1.05, 1.25)
            
        crash_point = round(val, 2)
            
        # Asegurar límites razonables para el bot (mínimo 1.0, máximo 25.0)
        crash_point = min(25.0, crash_point)
        current_mult = 1.00

        ticket_activo = False
        msg_cooldown_ticket = ""
        if apuesta <= CRASH_TICKET_MAX_BET:
            from src.db import usuario_tiene_item, usar_item_usuario, check_and_register_shield_use
            if await asyncio.to_thread(usuario_tiene_item, user_id, CRASH_TICKET_ITEM_ID):
                status, time_remaining = await asyncio.to_thread(check_and_register_shield_use, user_id)
                if status == 'ok' or status == 'blocked_start':
                    ticket_activo = await asyncio.to_thread(usar_item_usuario, user_id, CRASH_TICKET_ITEM_ID)
                    if status == 'blocked_start' and ticket_activo:
                        msg_cooldown_ticket = "⏱️ **Has alcanzado el límite de 3 escudos diarios.** Cooldown de 24h iniciado."
                else:
                    hours = time_remaining // 3600
                    minutes = (time_remaining % 3600) // 60
                    msg_cooldown_ticket = f"⚠️ **No se pudo usar tu Ticket de Crash.** Bloqueado por cooldown de escudos ({hours}h {minutes:02d}m restantes)."

        desc_msg = (
            f"💰 **Apuesta:** {apuesta} monedas\n"
            f"📈 **Multiplicador actual:** x{current_mult:.2f}\n\n"
            f"🎯 El multiplicador empezará en x1.00 y subirá hasta explotar\n"
            f"⚡ **¡Puede explotar en cualquier momento!**\n"
            f"💡 Puedes retirarte desde el inicio - ¡Más riesgo, más recompensa!"
        )
        if msg_cooldown_ticket:
            desc_msg += f"\n\n{msg_cooldown_ticket}"

        embed = discord.Embed(
            title="💥 Crash Casino",
            description=desc_msg,
            color=discord.Color.orange()
        )
        view = CrashView(ctx_or_interaction, user, apuesta, saldo, crash_point, difficulty_modifier, difficulty_explanation, ticket_activo)
        
        if is_slash:
            msg = await ctx_or_interaction.followup.send(embed=embed, view=view)
        else:
            msg = await ctx_or_interaction.send(embed=embed, view=view)
            
        await view.run_crash(msg, embed)

class CrashView(discord.ui.View):
    def __init__(self, ctx_or_interaction, user, apuesta, saldo, crash_point, difficulty_modifier=0.0, difficulty_explanation="", ticket_activo=False):
        super().__init__(timeout=15)
        self.ctx_or_interaction = ctx_or_interaction
        self.user = user
        self.apuesta = apuesta
        self.saldo = saldo
        self.crash_point = crash_point
        self.difficulty_modifier = difficulty_modifier
        self.difficulty_explanation = difficulty_explanation
        self.ticket_activo = ticket_activo
        self.cobrado = False
        self.juego_terminado = False  # Nueva bandera para evitar condiciones de carrera
        self.msg = None
        self.embed = None
        self.current_mult = 1.00  # Empezar en 1.00x
        self.progress = []  # Para animación visual

    @discord.ui.button(label="Retirarse", style=discord.ButtonStyle.success)
    async def retirar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verificar permisos y estado del juego
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("No puedes usar este botón.", ephemeral=True)
            return
        
        # Evitar condiciones de carrera con atomic check-and-set
        if self.cobrado or self.juego_terminado:
            try:
                await interaction.response.send_message("El juego ya ha terminado.", ephemeral=True)
            except discord.InteractionResponded:
                await interaction.followup.send("El juego ya ha terminado.", ephemeral=True)
            return
        
        mult_al_retirarse = self.current_mult
        self.cobrado = True
        self.juego_terminado = True

        await interaction.response.defer()
        
        try:
            # --- MEJORAS BLACK MARKET ---
            ganancia_bonus = 1.0
            from src.db import usuario_tiene_mejora
            if await asyncio.to_thread(usuario_tiene_mejora, self.user.id, 3):  # Magnate
                ganancia_bonus += 0.15
            # ----------------------------
            
            ganancia_total = int(self.apuesta * mult_al_retirarse * ganancia_bonus)
            ganancia_neta = ganancia_total - self.apuesta
            
            # Actualizar balance
            nuevo_saldo = self.saldo + ganancia_total
            await asyncio.to_thread(add_balance, self.user.id, ganancia_total)
            await asyncio.to_thread(registrar_transaccion, self.user.id, ganancia_neta, f"Crash: retirado x{mult_al_retirarse:.2f}")
            
            # Registrar resultado para el sistema de dificultad
            await asyncio.to_thread(record_game_result, self.user.id, 'crash', self.apuesta, 
                             'win' if ganancia_neta > 0 else 'loss', 
                             max(0, ganancia_neta), self.difficulty_modifier, nuevo_saldo)
            
            try:
                await process_post_game_events(self.ctx_or_interaction, self.user.id, 'crash', self.apuesta, max(0, ganancia_neta))
            except Exception:
                pass
            
            # Determinar color y mensaje según si ganó o perdió
            if ganancia_neta > 0:
                color = discord.Color.green()
                resultado = f"✅ **¡GANASTE!** +{ganancia_neta} monedas"
            elif ganancia_neta < 0:
                color = discord.Color.red()
                resultado = f"❌ **Perdiste** {abs(ganancia_neta)} monedas"
            else:
                color = discord.Color.yellow()
                resultado = f"🟰 **Empate** (sin ganancias ni pérdidas)"
            
            resultado_embed = discord.Embed(
                title="💥 Crash Casino - Te retiraste",
                description=(
                    f"🎯 **Multiplicador final:** x{mult_al_retirarse:.2f}\n"  # Usar multiplicador capturado
                    f"💰 **Apuesta inicial:** {self.apuesta} monedas\n"
                    f"💵 **Total recibido:** {ganancia_total} monedas\n"
                    f"{resultado}\n"
                    f"💰 **Nuevo saldo:** {nuevo_saldo:,} monedas\n\n"
                    f"{self._progress_bar_blocks(min(15, len(self.progress)), 15, explosion=False)}"
                ),
                color=color
            )
            
            # Deshabilitar todos los botones
            for item in self.children:
                try:
                    item.disabled = True
                except AttributeError:
                    pass  # Algunos items pueden no tener disabled
            
            # Intentar responder a la interacción
            try:
                if interaction.response.is_done():
                    await interaction.edit_original_response(embed=resultado_embed, view=self)
                else:
                    await interaction.response.edit_message(embed=resultado_embed, view=self)
            except (discord.InteractionResponded, discord.NotFound, discord.HTTPException):
                # Si falla, intentar editar el mensaje directamente
                try:
                    if self.msg and hasattr(self.msg, 'edit'):
                        await self.msg.edit(embed=resultado_embed, view=self)
                    else:
                        await interaction.followup.send(embed=resultado_embed, ephemeral=True)
                except:
                    # Como último recurso, enviar un nuevo mensaje
                    await interaction.followup.send(embed=resultado_embed, ephemeral=True)
            
        except Exception as e:
            # En caso de error, enviar mensaje de error
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Error procesando el retiro. Contacta al administrador.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ Error procesando el retiro. Contacta al administrador.", ephemeral=True)
            except:
                pass
            raise
        finally:
            self.stop()

    async def run_crash(self, msg, embed):
        self.msg = msg
        self.embed = embed
        self.current_mult = 1.00  # Empezar en 1.00x (estándar de Crash)
        self.progress = []
        
        explosion = False
        
        try:
            # Si el crash_point es exactamente 1.0, explota instantáneamente
            if self.crash_point <= 1.0:
                explosion = True
            else:
                while True:
                    # VERIFICACIÓN ATÓMICA: si el juego terminó, salir inmediatamente
                    if self.cobrado or self.juego_terminado:
                        return
                    
                    # Determinar incremento y tiempo de espera según el multiplicador actual
                    if self.current_mult < 1.5:
                        increment = 0.10
                        sleep_time = 1.2
                        danger_msg = "🟢 **Zona segura** - ¡Buen momento para empezar!"
                    elif self.current_mult < 3.0:
                        increment = 0.20
                        sleep_time = 1.0
                        danger_msg = "🟡 **Zona de riesgo medio** - ¡Cuidado!"
                    elif self.current_mult < 6.0:
                        increment = 0.50
                        sleep_time = 1.0
                        danger_msg = "🟠 **Zona peligrosa** - ¡Considera retirarte!"
                    else:
                        increment = 1.00
                        sleep_time = 1.0
                        danger_msg = "🔴 **ZONA EXTREMA** - ¡MUY ARRIESGADO!"
                    
                    # Calcular el siguiente multiplicador
                    next_mult = round(self.current_mult + increment, 2)
                    
                    if next_mult >= self.crash_point:
                        # Llegamos al límite. Romper el bucle y actualizar al multiplicador exacto del crash.
                        self.current_mult = self.crash_point
                        break
                        
                    # Incrementar multiplicador
                    self.current_mult = next_mult
                    self.progress.append(self.current_mult)
                    
                    # Crear barra de progreso visual
                    progress_ratio = min(1.0, self.current_mult / max(self.crash_point, 5.0))
                    progress_visual = int(progress_ratio * 15)
                    bar = self._progress_bar_blocks(progress_visual, 15, explosion=False)
                    
                    embed.description = (
                        f"💰 **Apuesta:** {self.apuesta} monedas\n"
                        f"📈 **Multiplicador:** x{self.current_mult:.2f}\n"
                        f"{bar}\n"
                        f"{danger_msg}\n"
                        f"⚡ **¡RETÍRATE AHORA!** ¡Presiona el botón para cobrar!"
                    )
                    
                    # Verificar nuevamente antes de actualizar el mensaje de Discord
                    if not self.juego_terminado and self.msg:
                        try:
                            await self.msg.edit(embed=embed, view=self)
                        except Exception:
                            pass
                    
                    # Esperar antes del siguiente paso
                    await asyncio.sleep(sleep_time)
                
                # Si salió del bucle y no se ha cobrado, significa que llegó al crash_point
                if not self.cobrado and not self.juego_terminado:
                    explosion = True

            # Solo procesar el final del juego si no se ha cobrado ya
            if not self.cobrado and not self.juego_terminado:
                self.juego_terminado = True  # Marcar como terminado
                
                # Desactivar botones
                for item in self.children:
                    try:
                        item.disabled = True
                    except AttributeError:
                        pass
                
                if explosion:
                    # Crear barra visual para la explosión
                    progress_ratio = min(1.0, self.current_mult / max(self.crash_point, 5.0))
                    progress_visual = int(progress_ratio * 15)
                    bar = self._progress_bar_blocks(progress_visual, 15, explosion=True)
                    
                    # Registrar pérdida o reembolso
                    reembolsado = False
                    if self.ticket_activo and self.current_mult < 1.50:
                        reembolsado = True
                                
                    if reembolsado:
                        nuevo_saldo = self.saldo + self.apuesta
                        await asyncio.to_thread(add_balance, self.user.id, self.apuesta)
                        await asyncio.to_thread(registrar_transaccion, self.user.id, 0, f"Crash: Reembolso por Ticket (<1.5x) en x{self.current_mult:.2f}")
                        await asyncio.to_thread(record_game_result, self.user.id, 'crash', self.apuesta, 'refund', 0, self.difficulty_modifier, nuevo_saldo)
                        try:
                            await process_post_game_events(self.ctx_or_interaction, self.user.id, 'crash', self.apuesta, 0)
                        except Exception:
                            pass
                        
                        resultado_embed = discord.Embed(
                            title="🛡️ Crash Casino - ¡Salvado por Ticket!",
                            description=(
                                f"💥 ¡El multiplicador explotó en **x{self.current_mult:.2f}**!\n"
                                f"🎫 **¡Ticket de Suerte aplicado!** Se reembolsó tu apuesta de {self.apuesta} monedas por explotar antes de x1.50.\n"
                                f"💰 **Nuevo saldo:** {nuevo_saldo:,} monedas\n\n{bar}"
                            ),
                            color=discord.Color.blue()
                        )
                    else:
                        nuevo_saldo = self.saldo
                        await asyncio.to_thread(registrar_transaccion, self.user.id, -self.apuesta, f"Crash: explotó x{self.current_mult:.2f}")
                        await asyncio.to_thread(record_game_result, self.user.id, 'crash', self.apuesta, 'loss', 0, self.difficulty_modifier, nuevo_saldo)
                        try:
                            await process_post_game_events(self.ctx_or_interaction, self.user.id, 'crash', self.apuesta, 0)
                        except Exception:
                            pass
                        
                        resultado_embed = discord.Embed(
                            title="💥 Crash Casino - ¡Explotó!",
                            description=(
                                f"💥 ¡Crash! El multiplicador explotó en **x{self.current_mult:.2f}**\n"
                                f"❌ **Perdiste** {self.apuesta} monedas.\n"
                                f"💰 **Nuevo saldo:** {nuevo_saldo:,} monedas\n\n{bar}"
                            ),
                            color=discord.Color.red()
                        )
                else:
                    # Si llegó al final sin explotar, es una victoria automática
                    # --- MEJORAS BLACK MARKET ---
                    ganancia_bonus = 1.0
                    from src.db import usuario_tiene_mejora
                    if await asyncio.to_thread(usuario_tiene_mejora, self.user.id, 3):  # Magnate
                        ganancia_bonus += 0.15
                    # ----------------------------
                    
                    ganancia_total = int(self.apuesta * self.current_mult * ganancia_bonus)
                    ganancia_neta = ganancia_total - self.apuesta
                    
                    nuevo_saldo = self.saldo + ganancia_total
                    await asyncio.to_thread(add_balance, self.user.id, ganancia_total)
                    await asyncio.to_thread(registrar_transaccion, self.user.id, ganancia_neta, f"Crash: completó sin explotar x{self.current_mult:.2f}")
                    await asyncio.to_thread(record_game_result, self.user.id, 'crash', self.apuesta, 'win', ganancia_neta, self.difficulty_modifier, nuevo_saldo)
                    try:
                        await process_post_game_events(self.ctx_or_interaction, self.user.id, 'crash', self.apuesta, ganancia_neta)
                    except Exception:
                        pass
                    
                    # Barra completa para victoria
                    bar = self._progress_bar_blocks(15, 15, explosion=False)
                    resultado_embed = discord.Embed(
                        title="🎉 Crash Casino - ¡Victoria!",
                        description=(
                            f"🎉 ¡Increíble! Llegaste al final sin que explotara\n"
                            f"🎯 **Multiplicador final:** x{self.current_mult:.2f}\n"
                            f"✅ **¡GANASTE!** +{ganancia_neta:,} monedas\n"
                            f"💰 **Total recibido:** {ganancia_total:,} monedas\n"
                            f"💰 **Nuevo saldo:** {nuevo_saldo:,} monedas\n\n{bar}"
                        ),
                        color=discord.Color.gold()
                    )
                
                try:
                    if self.msg:
                        await self.msg.edit(embed=resultado_embed, view=self)
                except Exception:
                    try:
                        if self.msg:
                            await self.msg.channel.send(embed=resultado_embed)
                    except:
                        pass
                        
        except Exception as e:
            # En caso de error, marcar como terminado
            self.juego_terminado = True
            raise
        finally:
            self.stop()

    def _progress_bar_blocks(self, filled, total, explosion=False):
        filled = max(0, min(filled, total))  # Asegurar que esté en rango válido
        bar = '🟩' * filled + '⬜' * (total - filled)
        if explosion and filled > 0:
            bar = bar[:filled-1] + '💥' + bar[filled:]
        return f"[{bar}]"

async def setup(bot):
    await bot.add_cog(Crash(bot))
    print("Crash cog loaded successfully.")
