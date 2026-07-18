import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
from datetime import datetime

from src.db import ensure_user, get_user_prestige_level, get_flex_message, set_flex_message
from src.utils.prestige_config import PRESTIGE_TIERS

logger = logging.getLogger(__name__)


def _get_prestige_title(level: int) -> str:
    """Retorna el título del tier de Prestigio según el nivel."""
    for tier in PRESTIGE_TIERS:
        if tier["level"] == level:
            return tier["title"]
    return "Sin Prestigio"


class Flex(commands.Cog):
    """Comando /flex — exclusivo para usuarios con Prestigio I o superior."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="flex",
        description="Muestra tu tarjeta de Prestigio. Requiere Prestigio I."
    )
    @app_commands.describe(
        mensaje="Mensaje personalizado para tu tarjeta (máx. 100 caracteres). Opcional."
    )
    async def flex(self, interaction: discord.Interaction, mensaje: str = None):
        await interaction.response.defer()
        user_id = interaction.user.id
        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)

        # ── Gate: Prestigio I ──
        prestige_lvl = await asyncio.to_thread(get_user_prestige_level, user_id)
        if prestige_lvl < 1:
            embed = discord.Embed(
                title="🔒 Acceso Restringido",
                description=(
                    "El comando `/flex` es exclusivo para usuarios con **Prestigio I** o superior.\n\n"
                    "Usa `/prestigio` para ver tu progreso y cuándo puedes acceder."
                ),
                color=discord.Color.dark_gray()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # ── Si se provee un mensaje, guardarlo y confirmar ──
        if mensaje is not None:
            mensaje = mensaje[:100]
            await asyncio.to_thread(set_flex_message, user_id, mensaje)

            embed = discord.Embed(
                title="✅ Mensaje Flex actualizado",
                description=f"Tu mensaje ha sido guardado:\n> *{mensaje}*",
                color=discord.Color.green()
            )
            embed.set_footer(text="Usa /flex sin argumento para ver tu tarjeta.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # ── Mostrar la tarjeta de Flex ──
        flex_msg = await asyncio.to_thread(get_flex_message, user_id)
        titulo = _get_prestige_title(prestige_lvl)

        # Paleta de colores según nivel de Prestigio
        prestige_colors = {
            1: discord.Color.gold(),
            2: discord.Color.purple(),
            3: discord.Color.red(),
            4: discord.Color.teal(),
            5: discord.Color.dark_magenta(),
            6: discord.Color.blurple(),
            7: discord.Color.dark_gold(),
        }
        color = prestige_colors.get(prestige_lvl, discord.Color.gold())

        embed = discord.Embed(
            title=f"🌟 {interaction.user.display_name}",
            color=color,
            timestamp=discord.utils.utcnow() if hasattr(discord.utils, "utcnow") else datetime.now()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        embed.add_field(
            name="🏅 Rango de Prestigio",
            value=f"**Nivel {prestige_lvl}** — {titulo}",
            inline=False
        )

        if flex_msg:
            embed.add_field(
                name="💬 Mensaje",
                value=f"*\"{flex_msg}\"*",
                inline=False
            )
        else:
            embed.add_field(
                name="💬 Mensaje",
                value="*Sin mensaje personalizado — usa `/flex mensaje:<texto>` para añadir uno.*",
                inline=False
            )

        embed.set_footer(text="Tarjeta de Prestigio · /flex mensaje:<texto> para personalizar")
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Flex(bot))
    logger.info("Flex cog cargado exitosamente.")
