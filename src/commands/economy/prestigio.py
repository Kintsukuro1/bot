import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
from datetime import datetime

from src.db import ensure_user, get_balance, get_user_prestige_level
from src.utils.prestige_config import (
    PRESTIGE_TIERS,
    PRESTIGE_RESET_SEED,
    get_next_prestige_tier,
    can_prestige,
    do_prestige
)
from src.utils.cooldowns import ECONOMY_COOLDOWN

logger = logging.getLogger(__name__)


class PrestigeConfirmView(discord.ui.View):
    def __init__(self, user_id, next_tier):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.next_tier = next_tier
        self.confirmed = False

    @discord.ui.button(label="Confirmar Prestigio 🌟", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ No puedes tomar esta decisión por otra persona.", ephemeral=True)
            return

        await interaction.response.defer()
        self.confirmed = True
        
        success, message = await asyncio.to_thread(do_prestige, self.user_id)
        
        for item in self.children:
            item.disabled = True
        
        if success:
            embed = discord.Embed(
                title="🌟 ¡ASCENSO DE PRESTIGIO! 🌟",
                description=(
                    f"🎉 {interaction.user.mention} ha ascendido a **{self.next_tier['title']}**!\n\n"
                    f"{message}\n\n"
                    f"💡 *Tus niveles de trabajo, energía e inventario se mantienen intactos.*"
                ),
                color=discord.Color.purple()
            )
            await interaction.edit_original_response(embed=embed, view=None)
        else:
            embed = discord.Embed(
                title="❌ Error al Prestigiar",
                description=message,
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=embed, view=None)
            
        self.stop()

    async def on_timeout(self):
        self.confirmed = True
        for item in self.children:
            item.disabled = True
        self.stop()


class Prestigio(commands.Cog):
    """Cog para el Sistema de Prestigio."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="prestigio",
        description="Muestra tu nivel de prestigio actual o te permite prestigiar si cumples el umbral."
    )
    async def prestigio(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)

        lvl = await asyncio.to_thread(get_user_prestige_level, user_id)
        balance = await asyncio.to_thread(get_balance, user_id)
        
        # Buscar título del nivel de prestigio actual
        current_title = "Sin Prestigio"
        for t in PRESTIGE_TIERS:
            if t["level"] == lvl:
                current_title = t["title"]
                break

        next_tier = get_next_prestige_tier(user_id)
        ok, _ = can_prestige(user_id)

        embed = discord.Embed(
            title="🌟 Sistema de Prestigio 🌟",
            color=discord.Color.purple(),
            timestamp=discord.utils.utcnow() if hasattr(discord.utils, 'utcnow') else datetime.now()
        )
        
        embed.description = (
            f"👤 **Nivel de Prestigio:** `{lvl}`\n"
            f"🏅 **Título de Rango:** **{current_title}**\n"
            f"💰 **Saldo Actual:** `{balance:,}` monedas"
        )

        if next_tier:
            req = next_tier["threshold"]
            progreso_pct = min(100, int((balance / req) * 100))
            filled = min(10, progreso_pct // 10)
            bar = "█" * filled + "░" * (10 - filled)
            
            embed.add_field(
                name=f"🚀 Siguiente Nivel: {next_tier['title']} (Nivel {next_tier['level']})",
                value=(
                    f"🎯 **Umbral necesario:** `{req:,}` monedas\n"
                    f"📊 **Progreso:** `{bar}` {progreso_pct}%\n"
                    f"📉 **Faltan:** `{max(0, req - balance):,}` monedas"
                ),
                inline=False
            )
            
            if ok:
                embed.add_field(
                    name="⚠️ ¡Listo para ascender!",
                    value=(
                        f"Si decides prestigiar:\n"
                        f"1. Tu nivel de prestigio subirá a **{next_tier['level']}**.\n"
                        f"2. Tu balance se restablecerá a **{PRESTIGE_RESET_SEED:,}** monedas.\n"
                        f"3. Conservarás tu energía, niveles de trabajo, items e inventario.\n\n"
                        f"*¿Deseas confirmar la acción?*"
                    ),
                    inline=False
                )
                view = PrestigeConfirmView(user_id, next_tier)
                msg = await interaction.followup.send(embed=embed, view=view)
                # Guardar el mensaje para deshabilitar los botones al timeout
                async def disable_after_timeout():
                    await asyncio.sleep(60)
                    if not view.confirmed:
                        try:
                            for item in view.children:
                                item.disabled = True
                            await msg.edit(view=view)
                        except Exception:
                            pass
                asyncio.create_task(disable_after_timeout())
                return
            else:
                embed.add_field(
                    name="🔒 Requisitos",
                    value="No tienes suficientes monedas para alcanzar el siguiente nivel de prestigio.",
                    inline=False
                )
        else:
            embed.add_field(
                name="🏆 Nivel Máximo",
                value="¡Felicidades! Has alcanzado el nivel de prestigio máximo disponible.",
                inline=False
            )

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Prestigio(bot))
    logger.info("Cog Prestigio cargado exitosamente.")
