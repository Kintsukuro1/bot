import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import logging
from src.db import (
    get_balance, set_balance, deduct_balance, add_balance, ensure_user,
    registrar_transaccion, record_game_result, usuario_tiene_item,
    usar_item_usuario, check_and_register_shield_use, usuario_tiene_mejora,
    process_crash_payout_atomic, get_provably_fair_seeds, advance_provably_fair_nonce
)
from src.utils.provably_fair import get_uniform_float
from src.commands.economy.pets import process_post_game_events
from src.utils.dynamic_difficulty import DynamicDifficulty
from src.utils.cooldowns import CASINO_COOLDOWN

logger = logging.getLogger(__name__)

CRASH_TICKET_MAX_BET = 5000
CRASH_TICKET_ITEM_ID = 6

async def _send_crash_error(ctx_or_interaction, is_slash: bool, message: str):
    """Envía un mensaje de error para interacciones Slash o normal para comandos de prefijo."""
    if is_slash:
        try:
            await ctx_or_interaction.edit_original_response(content=message)
        except (discord.NotFound, discord.HTTPException, discord.InteractionResponded) as e:
            logger.warning("No se pudo editar la respuesta original para enviar el error en crash: %s", str(e))
            try:
                await ctx_or_interaction.followup.send(message, ephemeral=True)
            except (discord.NotFound, discord.HTTPException) as fe:
                logger.error("No se pudo enviar el error por followup en crash: %s", str(fe))
    else:
        await ctx_or_interaction.send(message)

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
            await _send_crash_error(ctx_or_interaction, is_slash, "❌ La apuesta debe ser mayor a 0.")
            return

        success, saldo_post_apuesta = await asyncio.to_thread(deduct_balance, user_id, apuesta)
        if not success:
            await _send_crash_error(ctx_or_interaction, is_slash, "❌ No tienes suficiente saldo para esa apuesta.")
            return
        # Calcular dificultad dinámica
        difficulty_modifier, difficulty_explanation = await asyncio.to_thread(
            DynamicDifficulty.calculate_dynamic_difficulty, user_id, apuesta, 'crash'
        )
        
        # Determinar la base del crash point usando una distribución de probabilidad realista
        # House edge base del 4% (ventaja de la casa)
        base_edge = 0.04
        # Ajustar la ventaja de la casa según la dificultad del jugador (-0.5 a 0.5)
        # Reducimos el rango de influencia de difficulty_modifier a 0.015 en vez de 0.06 (Opción A)
        edge = base_edge + (difficulty_modifier * 0.015)
        edge = max(0.01, min(0.15, edge))
        
        # Migración a Provably Fair
        seeds = await asyncio.to_thread(get_provably_fair_seeds, user_id)
        nonce = await asyncio.to_thread(advance_provably_fair_nonce, user_id)
        U = get_uniform_float(seeds["server_seed"], seeds["client_seed"], nonce, cursor=0)
        
        # Evitar división por cero y evitar valores extremos en la cola,
        # pero sin comprimir en exceso la cola de multiplicadores altos.
        U_adj = min(max(U, 1e-6), 0.9999)
        
        # Algoritmo clásico y justo de Crash: M = (1 - edge) / (1 - U)
        val = (1.0 - edge) / (1.0 - U_adj)
        
        # Piso absoluto de 1.00 si el cálculo da menos (no convertir en ganancia)
        crash_point = max(1.00, round(val, 2))
            
        # Asegurar límites razonables para el bot (mínimo 1.0, máximo 1000.0)
        crash_point = min(1000.0, crash_point)
        current_mult = 1.00

        ticket_activo = False
        msg_cooldown_ticket = ""
        if apuesta <= CRASH_TICKET_MAX_BET:
            if await asyncio.to_thread(usuario_tiene_item, user_id, CRASH_TICKET_ITEM_ID):
                status, time_remaining = await asyncio.to_thread(check_and_register_shield_use, user_id)
                if status == 'ok' or status == 'blocked_start':
                    ticket_activo = await asyncio.to_thread(usar_item_usuario, user_id, CRASH_TICKET_ITEM_ID)
                    if not ticket_activo:
                        msg_cooldown_ticket = (
                            "⚠️ **Ocurrió un problema al usar tu Ticket de Crash.** "
                            "No se aplicarán sus efectos en esta ronda. Intenta nuevamente más tarde."
                        )
                        logger.warning(
                            "Fallo al consumir crash ticket para user_id=%s. status=%s",
                            user_id, status
                        )
                    elif status == 'blocked_start':
                        msg_cooldown_ticket = (
                            "⏱️ **Has alcanzado el límite de 3 usos diarios de Ticket.** "
                            "Cooldown de 24h iniciado."
                        )
                else:
                    if status == 'error':
                        msg_cooldown_ticket = "⚠️ **No se pudo usar tu Ticket de Crash debido a un error de base de datos.**"
                    else:
                        hours = time_remaining // 3600
                        minutes = (time_remaining % 3600) // 60
                        msg_cooldown_ticket = f"⚠️ **No se pudo usar tu Ticket de Crash.** Bloqueado por cooldown de ticket ({hours}h {minutes:02d}m restantes)."

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
        view = CrashView(ctx_or_interaction, user, apuesta, saldo_post_apuesta, crash_point, difficulty_modifier, difficulty_explanation, ticket_activo)
        
        if is_slash:
            msg = await ctx_or_interaction.followup.send(embed=embed, view=view)
        else:
            msg = await ctx_or_interaction.send(embed=embed, view=view)
            
        await view.run_crash(msg, embed)

class CrashView(discord.ui.View):
    def __init__(self, ctx_or_interaction, user, apuesta, saldo_post_apuesta, crash_point, difficulty_modifier=0.0, difficulty_explanation="", ticket_activo=False):
        super().__init__(timeout=120)
        self.ctx_or_interaction = ctx_or_interaction
        self.user = user
        self.apuesta = apuesta
        self.saldo_post_apuesta = saldo_post_apuesta
        self.crash_point = crash_point
        self.difficulty_modifier = difficulty_modifier
        self.difficulty_explanation = difficulty_explanation
        self.ticket_activo = ticket_activo
        self.cobrado = False
        self.juego_terminado = False
        self.msg = None
        self.embed = None
        self.current_mult = 1.00  # Empezar en 1.00x
        self.progress_steps = 0  # Para animación visual
        self.crash_mult = None  # Multiplicador definitivo cuando el juego hace crash
        self._state_lock = asyncio.Lock()

    async def _get_ganancia_bonus(self) -> float:
        """Calcula el bono de ganancia basado en mejoras del mercado negro."""
        ganancia_bonus = 1.0
        if await asyncio.to_thread(usuario_tiene_mejora, self.user.id, 3):  # Magnate
            ganancia_bonus += 0.15
        if await asyncio.to_thread(usuario_tiene_mejora, self.user.id, 10):  # Corona
            ganancia_bonus += 0.05
        return ganancia_bonus

    async def _safe_edit_or_followup(self, interaction: discord.Interaction | None, embed: discord.Embed):
        """Edita de forma segura el mensaje del juego o envía un followup en caso de fallo,
        evitando duplicación de lógica y manejando excepciones de red.
        """
        if interaction is not None:
            try:
                if interaction.response.is_done():
                    # edit_original_response actualiza el mensaje y mantiene self.msg sincronizado como fuente de verdad
                    self.msg = await interaction.edit_original_response(embed=embed, view=self)
                else:
                    await interaction.response.edit_message(embed=embed, view=self)
            except (discord.NotFound, discord.HTTPException, discord.InteractionResponded) as e:
                logger.warning(
                    "Fallo al usar interaction para editar: %s. Reintentando con self.msg.edit",
                    str(e)
                )
                if self.msg and hasattr(self.msg, "edit"):
                    try:
                        await self.msg.edit(embed=embed, view=self)
                    except Exception:
                        pass
        else:
            try:
                if self.msg and hasattr(self.msg, 'edit'):
                    await self.msg.edit(embed=embed, view=self)
            except discord.NotFound:
                pass
            except discord.HTTPException as e:
                logger.warning(
                    "HTTPException al editar mensaje final en run_crash: %s (status=%s)",
                    getattr(e, "text", str(e)),
                    getattr(e, "status", "desconocido"),
                )
            except Exception as e:
                logger.exception("Error al editar mensaje final de Crash")

    async def _finalizar_juego(self, motivo: str, interaction: discord.Interaction | None = None):
        """Centraliza la lógica de finalización del juego para evitar condiciones de carrera."""
        async with self._state_lock:
            if self.cobrado or self.juego_terminado:
                return

            # Congelar el multiplicador definitivo de crash si aún no se ha fijado
            if self.crash_mult is None:
                self.crash_mult = self.current_mult

            if motivo == "retiro":
                self.cobrado = True
            self.juego_terminado = True

            # Deshabilitar todos los botones
            for item in self.children:
                try:
                    item.disabled = True
                except AttributeError:
                    pass  # Algunos items pueden no tener disabled

            mult_final = self.crash_mult

        try:
            if motivo == "retiro":
                # --- MEJORAS BLACK MARKET ---
                ganancia_bonus = await self._get_ganancia_bonus()
                # ----------------------------
                
                ganancia_total = int(self.apuesta * mult_final * ganancia_bonus)
                ganancia_neta = ganancia_total - self.apuesta
                
                # Actualizar balance y estadísticas atómicamente
                nuevo_saldo = self.saldo_post_apuesta + ganancia_total
                await asyncio.to_thread(
                    process_crash_payout_atomic,
                    self.user.id,
                    self.apuesta,
                    ganancia_total,
                    ganancia_neta,
                    'win' if ganancia_neta > 0 else 'loss',
                    self.difficulty_modifier,
                    nuevo_saldo,
                    f"Crash: retirado x{mult_final:.2f}"
                )
                
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
                        f"🎯 **Multiplicador final:** x{mult_final:.2f}\n"  # Usar multiplicador capturado
                        f"💰 **Apuesta inicial:** {self.apuesta} monedas\n"
                        f"💵 **Total recibido:** {ganancia_total} monedas\n"
                        f"{resultado}\n"
                        f"💰 **Nuevo saldo:** {nuevo_saldo:,} monedas\n\n"
                        f"{self._progress_bar_blocks(min(15, self.progress_steps), 15, explosion=False)}"
                    ),
                    color=color
                )
                
            elif motivo == "explosion":
                # Crear barra visual para la explosión
                progress_ratio = min(1.0, mult_final / max(self.crash_point, 5.0))
                progress_visual = int(progress_ratio * 15)
                # Asegurar al menos 1 bloque lleno si explotó, para que se muestre el icono de explosión 💥
                progress_visual = max(1, progress_visual)
                bar = self._progress_bar_blocks(progress_visual, 15, explosion=True)
                
                # Registrar pérdida o reembolso
                reembolsado = False
                if self.ticket_activo and mult_final <= 1.50:
                    reembolsado = True
                            
                if reembolsado:
                    nuevo_saldo = self.saldo_post_apuesta + self.apuesta
                    await asyncio.to_thread(
                        process_crash_payout_atomic,
                        self.user.id,
                        self.apuesta,
                        self.apuesta,
                        0,
                        'refund',
                        self.difficulty_modifier,
                        nuevo_saldo,
                        f"Crash: Reembolso por Ticket (<=1.5x) en x{mult_final:.2f}"
                    )
                    try:
                        await process_post_game_events(self.ctx_or_interaction, self.user.id, 'crash', self.apuesta, 0)
                    except Exception:
                        pass
                    
                    resultado_embed = discord.Embed(
                        title="🛡️ Crash Casino - ¡Salvado por Ticket!",
                        description=(
                            f"💥 ¡El multiplicador explotó en **x{mult_final:.2f}**!\n"
                            f"🎫 **¡Ticket de Suerte aplicado!** Se reembolsó tu apuesta de {self.apuesta} monedas por explotar en x1.50 o menos.\n"
                            f"💰 **Nuevo saldo:** {nuevo_saldo:,} monedas\n\n{bar}"
                        ),
                        color=discord.Color.blue()
                    )
                else:
                    nuevo_saldo = self.saldo_post_apuesta
                    await asyncio.to_thread(
                        process_crash_payout_atomic,
                        self.user.id,
                        self.apuesta,
                        0,
                        -self.apuesta,
                        'loss',
                        self.difficulty_modifier,
                        nuevo_saldo,
                        f"Crash: explotó x{mult_final:.2f}"
                    )
                    try:
                        await process_post_game_events(self.ctx_or_interaction, self.user.id, 'crash', self.apuesta, 0)
                    except Exception:
                        pass
                    
                    resultado_embed = discord.Embed(
                        title="💥 Crash Casino - ¡Explotó!",
                        description=(
                            f"💥 ¡Crash! El multiplicador explotó en **x{mult_final:.2f}**\n"
                            f"❌ **Perdiste** {self.apuesta} monedas.\n"
                            f"💰 **Nuevo saldo:** {nuevo_saldo:,} monedas\n\n{bar}"
                        ),
                        color=discord.Color.red()
                    )
            elif motivo == "completado":
                # --- MEJORAS BLACK MARKET ---
                ganancia_bonus = await self._get_ganancia_bonus()
                # ----------------------------
                
                ganancia_total = int(self.apuesta * mult_final * ganancia_bonus)
                ganancia_neta = ganancia_total - self.apuesta
                
                nuevo_saldo = self.saldo_post_apuesta + ganancia_total
                await asyncio.to_thread(
                    process_crash_payout_atomic,
                    self.user.id,
                    self.apuesta,
                    ganancia_total,
                    ganancia_neta,
                    'win',
                    self.difficulty_modifier,
                    nuevo_saldo,
                    f"Crash: completó sin explotar x{mult_final:.2f}"
                )
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
                        f"🎯 **Multiplicador final:** x{mult_final:.2f}\n"
                        f"✅ **¡GANASTE!** +{ganancia_neta:,} monedas\n"
                        f"💰 **Total recibido:** {ganancia_total:,} monedas\n"
                        f"💰 **Nuevo saldo:** {nuevo_saldo:,} monedas\n\n{bar}"
                    ),
                    color=discord.Color.gold()
                )
            elif motivo == "error":
                try:
                    await asyncio.to_thread(
                        process_crash_payout_atomic,
                        self.user.id,
                        self.apuesta,
                        self.apuesta,
                        0,
                        'refund',
                        0.0,
                        self.saldo_post_apuesta + self.apuesta,
                        "Crash: Reembolso por error de sistema"
                    )
                except Exception as db_err:
                    logger.exception(
                        "Error al intentar reembolsar tras fallo en Crash",
                        extra={
                            "user_id": self.user.id,
                            "apuesta": self.apuesta,
                            "saldo": self.saldo_post_apuesta,
                            "motivo": "error",
                        },
                    )
                
                resultado_embed = discord.Embed(
                    title="⚠️ Crash - Juego Cancelado",
                    description=(
                        f"Ocurrió un error inesperado al procesar el juego de Crash.\n"
                        f"**Tu apuesta de {self.apuesta} monedas ha sido devuelta.**"
                    ),
                    color=discord.Color.orange()
                )

            await self._safe_edit_or_followup(interaction, resultado_embed)
        finally:
            self.stop()

    @discord.ui.button(label="Retirarse", style=discord.ButtonStyle.success)
    async def retirar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verificar permisos y estado del juego
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("No puedes usar este botón.", ephemeral=True)
            return

        async with self._state_lock:
            # Si el juego ya terminó o el usuario ya cobró, avisar y salir
            if self.cobrado or self.juego_terminado:
                try:
                    await interaction.response.send_message("El juego ya ha terminado.", ephemeral=True)
                except discord.InteractionResponded:
                    await interaction.followup.send("El juego ya ha terminado.", ephemeral=True)
                return

        # Deferimos la interacción antes de proceder (fuera del lock para no bloquear el loop)
        await interaction.response.defer()

        # Finalizar el juego por retiro (llamado fuera del lock)
        await self._finalizar_juego(motivo="retiro", interaction=interaction)

    async def run_crash(self, msg, embed):
        self.msg = msg
        self.embed = embed
        self.current_mult = 1.00  # Empezar en 1.00x (estándar de Crash)
        self.progress_steps = 0
        
        explosion = False
        
        try:
            # Si el crash_point es exactamente 1.0, explota instantáneamente
            if self.crash_point <= 1.0:
                explosion = True
                if self.progress_steps < 1:
                    self.progress_steps = 1
            else:
                while True:
                    # VERIFICACIÓN ATÓMICA: si el juego terminó, salir inmediatamente
                    async with self._state_lock:
                        if self.cobrado or self.juego_terminado or self.crash_mult is not None:
                            return
                        curr_mult = self.current_mult
                    
                    # Determinar incremento y tiempo de espera según el multiplicador actual
                    if curr_mult < 1.5:
                        increment = 0.10
                        sleep_time = 1.2
                        danger_msg = "🟢 **Zona segura** - ¡Buen momento para empezar!"
                    elif curr_mult < 3.0:
                        increment = 0.20
                        sleep_time = 1.0
                        danger_msg = "🟡 **Zona de riesgo medio** - ¡Cuidado!"
                    elif curr_mult < 6.0:
                        increment = 0.50
                        sleep_time = 1.0
                        danger_msg = "🟠 **Zona peligrosa** - ¡Considera retirarte!"
                    else:
                        increment = 1.00
                        sleep_time = 1.0
                        danger_msg = "🔴 **ZONA EXTREMA** - ¡MUY ARRIESGADO!"
                    
                    # Calcular el siguiente multiplicador
                    next_mult = round(curr_mult + increment, 2)
                    
                    if next_mult >= self.crash_point:
                        # Llegamos al límite. Romper el bucle y actualizar al multiplicador exacto del crash.
                        async with self._state_lock:
                            if self.cobrado or self.juego_terminado or self.crash_mult is not None:
                                return
                            self.current_mult = self.crash_point
                            self.crash_mult = self.crash_point
                            curr_mult = self.current_mult
                        break
                        
                    # Incrementar multiplicador
                    async with self._state_lock:
                        if self.cobrado or self.juego_terminado or self.crash_mult is not None:
                            return
                        self.current_mult = next_mult
                        self.progress_steps += 1
                        curr_mult = self.current_mult
                    
                    # Crear barra de progreso visual
                    progress_ratio = min(1.0, curr_mult / max(self.crash_point, 5.0))
                    progress_visual = int(progress_ratio * 15)
                    bar = self._progress_bar_blocks(progress_visual, 15, explosion=False)
                    
                    embed.description = (
                        f"💰 **Apuesta:** {self.apuesta} monedas\n"
                        f"📈 **Multiplicador:** x{curr_mult:.2f}\n"
                        f"{bar}\n"
                        f"{danger_msg}\n"
                        f"⚡ **¡RETÍRATE AHORA!** ¡Presiona el botón para cobrar!"
                    )
                    
                    # Verificar nuevamente el estado bajo el lock y decidir si editar
                    async with self._state_lock:
                        should_edit = not self.juego_terminado and self.msg is not None and self.crash_mult is None
                        msg_to_edit = self.msg if should_edit else None
                    
                    # Hacer el await fuera del lock para no bloquear otras interacciones
                    if msg_to_edit is not None:
                        try:
                            await msg_to_edit.edit(embed=embed, view=self)
                        except Exception:
                            # Ignorar errores de edición (por ejemplo, mensajes borrados o rate limits)
                            pass
                    
                    # Esperar antes del siguiente paso
                    await asyncio.sleep(sleep_time)
                
                # Si salió del bucle y no se ha cobrado, significa que llegó al crash_point
                async with self._state_lock:
                    if not self.cobrado and not self.juego_terminado:
                        explosion = True
 
            # Solo procesar el final del juego si no se ha cobrado ya
            await self._finalizar_juego(motivo="explosion" if explosion else "completado")
                        
        except Exception as e:
            await self._finalizar_juego(motivo="error")
            logger.exception("Error crítico en Crash (run_crash)")
            raise
        finally:
            self.stop()

    def _progress_bar_blocks(self, filled, total, explosion=False):
        filled = max(0, min(filled, total))  # Asegurar que esté en rango válido
        blocks = ['🟩'] * filled + ['⬜'] * (total - filled)
        if explosion and filled > 0:
            blocks[filled - 1] = '💥'
        bar = "".join(blocks)
        return f"[{bar}]"

async def setup(bot):
    await bot.add_cog(Crash(bot))
    print("Crash cog loaded successfully.")
