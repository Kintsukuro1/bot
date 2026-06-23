import discord
from discord.ext import commands
from discord import app_commands

class Slowmode(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="slowmode", description="Establece el slowmode del canal actual (en segundos).")
    @app_commands.describe(seconds="Cantidad de segundos para el slowmode (0 para desactivar, máx 21600)")
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, seconds: int):
        if seconds < 0 or seconds > 21600:
            await interaction.response.send_message("❌ El slowmode debe estar entre 0 y 21600 segundos (6 horas).", ephemeral=True)
            return

        try:
            await interaction.channel.edit(slowmode_delay=seconds)
            if seconds == 0:
                msg = "⏱️ Slowmode desactivado en este canal."
            else:
                msg = f"⏱️ Slowmode establecido a {seconds} segundos en este canal."
            await interaction.response.send_message(msg, ephemeral=False)
        except discord.Forbidden:
            await interaction.response.send_message("❌ No tengo permisos suficientes para cambiar el slowmode en este canal.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Ocurrió un error al intentar cambiar el slowmode: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Slowmode(bot))