import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from src.db import get_balance, set_balance, ensure_user, registrar_transaccion, record_game_result
from src.utils.dynamic_difficulty import DynamicDifficulty

class Crash(commands.Cog):
    """Cog para el juego Crash."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="crash", description="Juega Crash: apuesta y retírate antes de que el multiplicador explote!")
    @app_commands.describe(apuesta="Cantidad de monedas a apostar")
    async def crash_slash(self, interaction: discord.Interaction, apuesta: int):
        await self._crash_game(interaction, apuesta, is_slash=True)

    @commands.command(name="crash", help="Juega Crash: apuesta y retírate antes de que el multiplicador explote! Uso: !crash <apuesta>")
    async def crash(self, ctx, apuesta: int):
        await self._crash_game(ctx, apuesta, is_slash=False)

    async def _crash_game(self, ctx_or_interaction, apuesta: int, is_slash: bool = False):
        if is_slash:
            user = ctx_or_interaction.user
            user_id = user.id
            user_name = user.name
        else:
            user = ctx_or_interaction.author
            user_id = user.id
            user_name = user.name
            
        ensure_user(user_id, user_name)  # Asegura registro y datos del usuario
        saldo = get_balance(user_id)
        
        if apuesta <= 0:
            error_msg = "❌ La apuesta debe ser mayor a 0."
            if is_slash:
                await ctx_or_interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await ctx_or_interaction.send(error_msg)
            return
            
        if apuesta > saldo:
            error_msg = f"❌ No tienes suficiente saldo para esa apuesta. Tu saldo: {saldo:,} monedas."
            if is_slash:
                await ctx_or_interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await ctx_or_interaction.send(error_msg)
            return
        # Calcular dificultad dinámica
        difficulty_modifier, difficulty_explanation = DynamicDifficulty.calculate_dynamic_difficulty(
            user_id, apuesta, 'crash'
        )
        
        # Ajustar el crash point basado en dificultad con mayor impacto
        base_min = 1.2
        base_max = 10.0

        if difficulty_modifier > 0:
            # Más difícil: reducir rango máximo significativamente
            crash_max = base_max * (1.0 - difficulty_modifier * 0.8)
            crash_min = base_min * (1.0 + difficulty_modifier * 0.3)  # También aumentar mínimo
        else:
            # Más fácil: aumentar rango máximo moderadamente
            crash_max = base_max * (1.0 - difficulty_modifier * 0.5)
            crash_min = base_min * (1.0 + difficulty_modifier * 0.1)

        # Asegurar límites mínimos/máximos
        crash_min = max(1.1, min(2.5, crash_min))
        crash_max = max(2.0, min(15.0, crash_max))

        crash_point = round(random.uniform(crash_min, crash_max), 2)
        current_mult = 0.25  # Empezar en 0.25x para dar tiempo de reacción
        
        embed = discord.Embed(
            title="💥 Crash Casino",
            description=(
                f"💰 **Apuesta:** {apuesta} monedas\n"
                f"📈 **Multiplicador actual:** x{current_mult:.2f}\n"
                f"📊 {difficulty_explanation}\n\n"
                f"🎯 El multiplicador empezará en x0.25 y subirá hasta explotar\n"
                f"⚡ **¡Puede explotar en cualquier momento!**\n"
                f"💡 Puedes retirarte desde el inicio - ¡Más riesgo, más recompensa!"
            ),
            color=discord.Color.orange()
        )
        view = CrashView(user, apuesta, saldo, crash_point, difficulty_modifier, difficulty_explanation)
        
        if is_slash:
            await ctx_or_interaction.response.send_message(embed=embed, view=view)
            # Obtener el mensaje para pasarlo a la vista
            msg = await ctx_or_interaction.original_response()
        else:
            msg = await ctx_or_interaction.send(embed=embed, view=view)
            
        await view.run_crash(msg, embed)

class CrashView(discord.ui.View):
    def __init__(self, user, apuesta, saldo, crash_point, difficulty_modifier=0.0, difficulty_explanation=""):
        super().__init__(timeout=15)
        self.user = user
        self.apuesta = apuesta
        self.saldo = saldo
        self.crash_point = crash_point
        self.difficulty_modifier = difficulty_modifier
        self.difficulty_explanation = difficulty_explanation
        self.cobrado = False
        self.juego_terminado = False  # Nueva bandera para evitar condiciones de carrera
        self.msg = None
        self.embed = None
        self.current_mult = 0.25  # Empezar en 0.25x
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
        
        # CAPTURA INSTANTÁNEA del multiplicador actual para evitar cambios del bucle
        mult_al_retirarse = self.current_mult
        
        # Marcar como cobrado inmediatamente para evitar doble ejecución
        self.cobrado = True
        self.juego_terminado = True
        
        try:
            ganancia_total = int(self.apuesta * mult_al_retirarse)  # Usar multiplicador capturado
            ganancia_neta = ganancia_total - self.apuesta  # Lo que realmente ganaste/perdiste
            
            # Actualizar balance
            nuevo_saldo = self.saldo - self.apuesta + ganancia_total
            set_balance(self.user.id, nuevo_saldo)
            registrar_transaccion(self.user.id, ganancia_neta, f"Crash: retirado x{mult_al_retirarse:.2f}")  # Usar multiplicador capturado
            
            # Registrar resultado para el sistema de dificultad
            record_game_result(self.user.id, 'crash', self.apuesta, 
                             'win' if ganancia_neta > 0 else 'loss', 
                             max(0, ganancia_neta), self.difficulty_modifier, nuevo_saldo)
            
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
                    f"📊 {self.difficulty_explanation}\n"
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
                if not interaction.response.is_done():
                    await interaction.response.edit_message(embed=resultado_embed, view=self)
                else:
                    # Usar followup solo si hay un mensaje válido
                    if interaction.message and hasattr(interaction.message, 'id'):
                        await interaction.followup.edit_message(interaction.message.id, embed=resultado_embed, view=self)
                    elif self.msg and hasattr(self.msg, 'edit'):
                        await self.msg.edit(embed=resultado_embed, view=self)
                    else:
                        await interaction.followup.send(embed=resultado_embed, ephemeral=True)
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
        finally:
            self.stop()

    async def run_crash(self, msg, embed):
        self.msg = msg
        self.embed = embed
        self.current_mult = 0.25  # Empezar en 0.25x
        self.progress = []
        
        # Sistema de incrementos con mayor impacto de dificultad
        increment_steps = [
            # (target_mult, sleep_time, increment)
            (1.0, 0.6, 0.25),
            (2.5, 0.5, 0.25),
            (5.0, 0.4, 0.25),
            (10.0, 0.3, 0.5)
        ]
        
        # Base explosion probabilities with stronger difficulty impact
        base_probabilities = {
            0.25: 0.005,
            1.0: 0.01,
            2.5: 0.03,
            5.0: 0.08,
            10.0: 0.15
        }
        
        explosion = False
        step_count = 0
        
        try:
            for target_mult, sleep_time, increment in increment_steps:
                # VERIFICACIÓN ATÓMICA: si el juego terminó, salir inmediatamente
                if self.cobrado or self.juego_terminado:
                    return
                
                while self.current_mult < target_mult and self.current_mult < self.crash_point:
                    # VERIFICACIÓN ATÓMICA antes de cada incremento
                    if self.cobrado or self.juego_terminado:
                        return
                    
                    # Incrementar multiplicador de forma gradual y predecible
                    self.current_mult = min(target_mult, self.current_mult + increment, self.crash_point)
                    self.progress.append(self.current_mult)
                    step_count += 1
                    
                    # Calcular probabilidad base según el rango actual
                    base_prob = 0.005  # Valor por defecto
                    for threshold, prob in sorted(base_probabilities.items()):
                        if self.current_mult >= threshold:
                            base_prob = prob
                        else:
                            break
                    
                    # Aplicar dificultad dinámica con mayor impacto
                    if self.difficulty_modifier > 0:
                        # Para dificultad alta: aumentar probabilidad de explosión más agresivamente
                        prob = base_prob * (1.0 + self.difficulty_modifier * 2.0)
                    else:
                        # Para dificultad baja: reducir probabilidad más moderadamente
                        prob = base_prob * (1.0 + self.difficulty_modifier * 0.8)
                    
                    # Ajuste adicional cerca del crash_point
                    if self.current_mult >= self.crash_point * 0.9:
                        prob += 0.35
                    elif self.current_mult >= self.crash_point * 0.8:
                        prob += 0.25
                    elif self.current_mult >= self.crash_point * 0.7:
                        prob += 0.15
                    
                    # Límites más estrictos
                    prob = max(0.01, min(0.95, prob))
                    
                    # Verificar explosión
                    if random.random() < prob:
                        explosion = True
                        break
                    
                    # Actualizar UI - crear barra de progreso más visual
                    progress_ratio = min(1.0, self.current_mult / max(self.crash_point, 5.0))
                    progress_visual = int(progress_ratio * 15)  # Reducir a 15 bloques máximo
                    bar = self._progress_bar_blocks(progress_visual, 15, explosion=False)
                    
                    # Mensaje dinámico según el multiplicador
                    if self.current_mult < 1.0:
                        danger_msg = "🟢 **Zona segura** - ¡Buen momento para empezar!"
                    elif self.current_mult < 2.5:
                        danger_msg = "🟡 **Zona de riesgo medio** - ¡Cuidado!"
                    elif self.current_mult < 5.0:
                        danger_msg = "🟠 **Zona peligrosa** - ¡Considera retirarte!"
                    else:
                        danger_msg = "🔴 **ZONA EXTREMA** - ¡MUY ARRIESGADO!"
                    
                    embed.description = (
                        f"💰 **Apuesta:** {self.apuesta} monedas\n"
                        f"📈 **Multiplicador:** x{self.current_mult:.2f}\n"
                        f"{bar}\n"
                        f"{danger_msg}\n"
                        f"⚡ **¡RETÍRATE AHORA!** ¡Presiona el botón para cobrar!"
                    )
                    
                    try:
                        # Verificar nuevamente antes de actualizar
                        if not self.juego_terminado and self.msg:
                            await self.msg.edit(embed=embed, view=self)
                    except Exception:
                        break
                    
                    # Sleep ajustado - más corto para fluidez
                    await asyncio.sleep(sleep_time)
                
                if explosion:
                    break
                    
                # Si llegamos al crash_point sin explotar, salir del loop
                if self.current_mult >= self.crash_point:
                    break
            
            # Solo procesar el final del juego si no se ha cobrado ya
            if not self.cobrado and not self.juego_terminado:
                self.juego_terminado = True  # Marcar como terminado
                
                # Desactivar botones
                for item in self.children:
                    try:
                        item.disabled = True
                    except AttributeError:
                        pass  # Algunos items pueden no tener disabled
                
                if explosion:
                    # Crear barra visual para la explosión
                    progress_ratio = min(1.0, self.current_mult / max(self.crash_point, 5.0))
                    progress_visual = int(progress_ratio * 15)
                    bar = self._progress_bar_blocks(progress_visual, 15, explosion=True)
                    
                    # Registrar pérdida
                    nuevo_saldo = self.saldo - self.apuesta
                    set_balance(self.user.id, nuevo_saldo)
                    registrar_transaccion(self.user.id, -self.apuesta, f"Crash: explotó x{self.current_mult:.2f}")
                    record_game_result(self.user.id, 'crash', self.apuesta, 'loss', 0, self.difficulty_modifier, nuevo_saldo)
                    
                    resultado_embed = discord.Embed(
                        title="💥 Crash Casino - ¡Explotó!",
                        description=(
                            f"💥 ¡Crash! El multiplicador explotó en **x{self.current_mult:.2f}**\n"
                            f"❌ **Perdiste** {self.apuesta} monedas.\n"
                            f"💰 **Nuevo saldo:** {nuevo_saldo:,} monedas\n"
                            f"📊 {self.difficulty_explanation}\n\n{bar}"
                        ),
                        color=discord.Color.red()
                    )
                else:
                    # Si llegó al final sin explotar, es una victoria automática
                    ganancia_total = int(self.apuesta * self.current_mult)
                    ganancia_neta = ganancia_total - self.apuesta
                    
                    nuevo_saldo = self.saldo - self.apuesta + ganancia_total
                    set_balance(self.user.id, nuevo_saldo)
                    registrar_transaccion(self.user.id, ganancia_neta, f"Crash: completó sin explotar x{self.current_mult:.2f}")
                    record_game_result(self.user.id, 'crash', self.apuesta, 'win', ganancia_neta, self.difficulty_modifier, nuevo_saldo)
                    
                    # Barra completa para victoria
                    bar = self._progress_bar_blocks(15, 15, explosion=False)
                    resultado_embed = discord.Embed(
                        title="🎉 Crash Casino - ¡Victoria!",
                        description=(
                            f"🎉 ¡Increíble! Llegaste al final sin que explotara\n"
                            f"🎯 **Multiplicador final:** x{self.current_mult:.2f}\n"
                            f"✅ **¡GANASTE!** +{ganancia_neta:,} monedas\n"
                            f"💰 **Total recibido:** {ganancia_total:,} monedas\n"
                            f"💰 **Nuevo saldo:** {nuevo_saldo:,} monedas\n"
                            f"📊 {self.difficulty_explanation}\n\n{bar}"
                        ),
                        color=discord.Color.gold()
                    )
                
                try:
                    if self.msg:
                        await self.msg.edit(embed=resultado_embed, view=self)
                except Exception:
                    # Si falla, intentar enviar un nuevo mensaje
                    try:
                        if self.msg:
                            await self.msg.channel.send(embed=resultado_embed)
                    except:
                        pass
                        
        except Exception as e:
            # En caso de error, marcar como terminado
            self.juego_terminado = True
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
