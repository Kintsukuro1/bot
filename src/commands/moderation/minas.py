from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import logging
from datetime import timedelta
from src.db import get_all_minas, set_minas_canal, registrar_mina_pisada

logger = logging.getLogger(__name__)

MAX_MINAS_POR_CANAL = 50
PROB_EXPLOSION = 0.02  # 2% de probabilidad por mensaje
PROB_FALLA = 0.10      # 10% de probabilidad de que la mina falle (dud)

class Minas(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Diccionario para almacenar las minas activas por canal {channel_id: cantidad}
        self.minas_activas = {}
        # Logger específico para este cog
        self.logger = logger
        # Locks por canal para evitar condiciones de carrera en operaciones concurrentes
        self._locks = {}

    def _get_lock_for_channel(self, channel_id: int) -> asyncio.Lock:
        """
        Obtiene (o crea) el lock asociado a un canal concreto.

        Mantener centralizada la creación de locks ayuda a controlar mejor
        el ciclo de vida de _locks.
        """
        lock = self._locks.get(channel_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[channel_id] = lock
        return lock

    def _cleanup_channel_state_if_empty(self, channel_id: int) -> None:
        """
        Elimina el estado asociado a un canal (incluyendo su lock) cuando
        ya no quedan minas activas en dicho canal.
        """
        minas_restantes = self.minas_activas.get(channel_id, 0)
        if minas_restantes <= 0:
            # Limpia minas y lock obsoletos para evitar crecimiento indefinido
            self.minas_activas.pop(channel_id, None)
            self._locks.pop(channel_id, None)

    async def cog_load(self):
        """Carga las minas desde la base de datos de manera asíncrona al cargar el cog."""
        try:
            self.minas_activas = await asyncio.to_thread(get_all_minas)
            self.logger.info(
                "[Minas] Minas cargadas desde la BD",
                extra={"minas_cargadas": len(self.minas_activas)}
            )
        except Exception:
            # Logeamos con traceback completo para facilitar el diagnóstico
            self.logger.exception(
                "[Minas] Error cargando minas desde DB",
                extra={"accion": "cargar_minas_db"}
            )
            self.minas_activas = {}
            raise

    def _validar_limite_minas(self, minas_actuales: int, cantidad: int) -> tuple[bool, str | None]:
        """
        Valida si se puede agregar `cantidad` de minas a las `minas_actuales` sin superar el límite.

        Retorna:
            (es_valido, mensaje_error)
        """
        nuevo_total = minas_actuales + cantidad
        if nuevo_total > MAX_MINAS_POR_CANAL:
            mensaje_error = (
                f"❌ No puedes poner tantas minas. El canal ya tiene {minas_actuales} minas "
                f"y el límite acumulado permitido es {MAX_MINAS_POR_CANAL} "
                f"(intentaste agregar {cantidad}, total {nuevo_total})."
            )
            return False, mensaje_error

        return True, None

    def _obtener_canal_texto(self, interaction: discord.Interaction, canal: discord.TextChannel = None) -> discord.TextChannel | None:
        """
        Valida y retorna un TextChannel válido a partir de un canal opcional o de la interacción.
        Retorna None si el canal no es del tipo discord.TextChannel o es None.
        """
        canal_obj = canal or interaction.channel
        if isinstance(canal_obj, discord.TextChannel):
            return canal_obj
        return None

    @app_commands.command(name="poner_minas", description="Coloca minas explosivas ocultas en un canal específico.")
    @app_commands.describe(
        cantidad="Número de minas a colocar",
        canal="El canal donde se colocarán las minas (opcional, por defecto el canal actual)"
    )
    @app_commands.default_permissions(administrator=True)
    async def poner_minas(self, interaction: discord.Interaction, cantidad: int, canal: discord.TextChannel = None):
        if cantidad <= 0:
            await interaction.response.send_message("❌ La cantidad de minas debe ser mayor a 0.", ephemeral=True)
            return

        canal_obj = self._obtener_canal_texto(interaction, canal)
        if canal_obj is None:
            await interaction.response.send_message("❌ Este comando solo se puede usar en canales de texto de servidores.", ephemeral=True)
            return

        canal_id = canal_obj.id
        lock = self._get_lock_for_channel(canal_id)
        async with lock:
            minas_actuales = self.minas_activas.get(canal_id, 0)
            es_valido, mensaje_error = self._validar_limite_minas(minas_actuales, cantidad)
            if not es_valido:
                await interaction.response.send_message(mensaje_error, ephemeral=True)
                return

            # Guardar en base de datos primero para evitar inconsistencias si falla
            try:
                await asyncio.to_thread(set_minas_canal, canal_id, minas_actuales + cantidad)
            except Exception:
                self.logger.exception(
                    "[Minas] Error al guardar minas en la base de datos al poner minas",
                    extra={"canal_id": canal_id, "cantidad": cantidad}
                )
                await interaction.response.send_message("❌ Ocurrió un error al guardar las minas en la base de datos.", ephemeral=True)
                return

            self.minas_activas[canal_id] = minas_actuales + cantidad

        embed = discord.Embed(
            title="💣 ¡Minas Colocadas!",
            description=f"Se han colocado **{cantidad}** minas en el canal {canal_obj.mention}.\n¡Tengan cuidado por dónde pisan!",
            color=discord.Color.dark_red()
        )
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignorar mensajes de bots
        if message.author.bot:
            return

        # Ignorar DMs u otros contextos sin guild
        if message.guild is None:
            return

        # Limitar la gestión de minas a canales de texto "clásicos"
        if not isinstance(message.channel, discord.TextChannel):
            return

        canal_id = message.channel.id

        # Intentar detonar una mina bajo lock para evitar condiciones de carrera
        lock = self._get_lock_for_channel(canal_id)
        mina_detonada = False
        minas_restantes = 0
        async with lock:
            # Si no hay minas en el canal, no hacer nada
            if canal_id not in self.minas_activas or self.minas_activas[canal_id] <= 0:
                return

            if random.random() < PROB_EXPLOSION:
                self.minas_activas[canal_id] -= 1
                minas_restantes = self.minas_activas[canal_id]
                if minas_restantes <= 0:
                    self._cleanup_channel_state_if_empty(canal_id)
                mina_detonada = True

        if not mina_detonada:
            return

        # Actualizar DB fuera del lock para evitar mantenerlo bloqueado en operaciones lentas
        try:
            await asyncio.to_thread(set_minas_canal, canal_id, minas_restantes)
        except Exception:
            self.logger.exception(
                "[Minas] Error al actualizar base de datos en on_message. Revertiendo decremento en memoria...",
                extra={"canal_id": canal_id, "minas_restantes_intentadas": minas_restantes}
            )
            # Revertir decremento en memoria bajo lock
            async with lock:
                self.minas_activas[canal_id] = self.minas_activas.get(canal_id, 0) + 1
            return

        # Probabilidad de que la mina falle (dud)
        mina_falla = random.random() < PROB_FALLA

        if mina_falla:
            embed_falla = discord.Embed(
                title="💥 *Click...*",
                description=f"{message.author.mention} pisó una mina...\n\n💨 **¡Qué alivio! La mina falló y no explotó.**",
                color=discord.Color.light_grey()
            )
            if minas_restantes > 0:
                embed_falla.set_footer(text=f"Aún quedan {minas_restantes} minas en el canal...")
                
            await message.channel.send(embed=embed_falla)
        else:
            # La mina explotó
            # Registrar que pisó una mina en la BD (manejamos la excepción para evitar cortar el flujo de on_message)
            try:
                await asyncio.to_thread(registrar_mina_pisada, message.author.id)
            except Exception:
                self.logger.exception(
                    "[Minas] Error al registrar mina pisada en la base de datos",
                    extra={"usuario_id": message.author.id}
                )

            # Intentar aplicar mute por 1 minuto (Timeout)
            timeout_duration = timedelta(minutes=1)
            mute_status = "success"  # "success", "forbidden", "http_error", "unexpected_error"
            
            try:
                await message.author.timeout(timeout_duration, reason="Pisó una mina explosiva.")
            except discord.Forbidden:
                mute_status = "forbidden"
            except discord.HTTPException:
                mute_status = "http_error"
                self.logger.exception(
                    "[Minas] Error HTTP al aplicar timeout",
                    extra={"usuario_id": message.author.id, "canal_id": canal_id}
                )
            except Exception:
                mute_status = "unexpected_error"
                self.logger.exception(
                    "[Minas] Error inesperado al aplicar timeout",
                    extra={"usuario_id": message.author.id, "canal_id": canal_id}
                )

            # Construir embed según el resultado del timeout
            if mute_status == "success":
                title_boom = "💥 ¡BBOOOM!"
                desc_boom = f"**¡{message.author.mention} activó una mina!**\nHa sido silenciado por 1 minuto tras la explosión. 🤕"
                color_boom = discord.Color.red()
            elif mute_status == "forbidden":
                title_boom = "💥 ¡BBOOOM!"
                desc_boom = f"**¡{message.author.mention} activó una mina!**\nPero es demasiado poderoso(a) y sobrevivió a la explosión sin ser silenciado(a) (Faltan permisos/Es administrador)."
                color_boom = discord.Color.orange()
            elif mute_status == "http_error":
                title_boom = "💥 ¡BBOOOM!"
                desc_boom = f"**¡{message.author.mention} activó una mina!**\nLa mina explotó, pero no se pudo aplicar el silencio debido a un error de comunicación con Discord. ⚠️"
                color_boom = discord.Color.orange()
            else:  # unexpected_error
                title_boom = "💥 ¡BBOOOM!"
                desc_boom = f"**¡{message.author.mention} activó una mina!**\nLa mina explotó, pero ocurrió un error inesperado al intentar aplicar el silencio. ⚠️"
                color_boom = discord.Color.orange()

            embed_boom = discord.Embed(
                title=title_boom,
                description=desc_boom,
                color=color_boom
            )
            if minas_restantes > 0:
                embed_boom.set_footer(text=f"Aún quedan {minas_restantes} minas en el canal...")

            await message.channel.send(embed=embed_boom)

    @app_commands.command(name="sacar_minas", description="Elimina todas las minas de un canal específico.")
    @app_commands.describe(
        canal="El canal donde se eliminarán las minas (opcional, por defecto el canal actual)"
    )
    @app_commands.default_permissions(administrator=True)
    async def sacar_minas(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        canal_obj = self._obtener_canal_texto(interaction, canal)
        if canal_obj is None:
            await interaction.response.send_message("❌ Este comando solo se puede usar en canales de texto de servidores.", ephemeral=True)
            return

        canal_id = canal_obj.id
        lock = self._get_lock_for_channel(canal_id)
        async with lock:
            if canal_id in self.minas_activas:
                # Guardar en base de datos primero para evitar inconsistencias si falla
                try:
                    await asyncio.to_thread(set_minas_canal, canal_id, 0)
                except Exception:
                    self.logger.exception(
                        "[Minas] Error al eliminar minas en la base de datos al sacar minas",
                        extra={"canal_id": canal_id}
                    )
                    await interaction.response.send_message("❌ Ocurrió un error al eliminar las minas en la base de datos.", ephemeral=True)
                    return

                self.minas_activas[canal_id] = 0
                self._cleanup_channel_state_if_empty(canal_id)
                minas_existian = True
            else:
                minas_existian = False

        if minas_existian:
            embed = discord.Embed(
                title="🧹 Minas Limpiadas",
                description=f"El escuadrón antibombas ha desactivado todas las minas en {canal_obj.mention}.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(f"✅ No hay minas en {canal_obj.mention}.", ephemeral=True)

    @app_commands.command(name="info_minas", description="Muestra la información de las minas en un canal específico.")
    @app_commands.describe(
        canal="El canal del que quieres ver la información (opcional, por defecto el canal actual)"
    )
    async def info_minas(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        canal_obj = self._obtener_canal_texto(interaction, canal)
        if canal_obj is None:
            await interaction.response.send_message("❌ Este comando solo se puede usar en canales de texto de servidores.", ephemeral=True)
            return

        canal_id = canal_obj.id

        minas_restantes = self.minas_activas.get(canal_id, 0)
        prob_explosion = int(PROB_EXPLOSION * 100)
        prob_falla = int(PROB_FALLA * 100)

        if minas_restantes > 0:
            embed = discord.Embed(
                title="💣 Información de Minas",
                description=f"Estado de las minas en {canal_obj.mention}:",
                color=discord.Color.orange()
            )
            embed.add_field(name="Minas Activas", value=f"**{minas_restantes}**", inline=False)
            embed.add_field(name="Probabilidad de Activar", value=f"**{prob_explosion}%** por cada mensaje enviado.", inline=False)
            embed.add_field(name="Probabilidad de Fallo (Dud)", value=f"**{prob_falla}%** si se activa la mina.", inline=False)
            embed.set_footer(text="¡Ten mucho cuidado por dónde pisas!")
        else:
            embed = discord.Embed(
                title="✅ Área Segura",
                description=f"No hay minas activas en {canal_obj.mention}.",
                color=discord.Color.green()
            )

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Minas(bot))
    logger.info("Minas cog loaded successfully.")
