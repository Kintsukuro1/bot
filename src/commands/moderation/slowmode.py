import discord
from discord.ext import commands

class Slowmode(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="slowmode", description="Establece el slowmode del canal actual (en segundos).")
    @discord.app_commands.describe(seconds="Cantidad de segundos para el slowmode (0 para desactivar)")
    async def slowmode(self, interaction: discord.Interaction, seconds: int):
        # Solo permite si el usuario tiene permisos de gestionar canales
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("No tienes permisos para usar este comando.", ephemeral=True)
            return

        if seconds < 0 or seconds > 21600:
            await interaction.response.send_message("El slowmode debe estar entre 0 y 21600 segundos (6 horas).", ephemeral=True)
            return

        await interaction.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            msg = "⏱️ Slowmode desactivado en este canal."
        else:
            msg = f"⏱️ Slowmode establecido a {seconds} segundos en este canal."
        await interaction.response.send_message(msg, ephemeral=False)

async def setup(bot):
    await bot.add_cog(Slowmode(bot))