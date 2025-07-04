import discord
from discord.ext import commands

class Purge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="purge", description="Elimina una cantidad de mensajes del canal actual.")
    @discord.app_commands.describe(amount="Cantidad de mensajes a eliminar (máx 100)")
    async def purge(self, interaction: discord.Interaction, amount: int):
        # Solo permite si el usuario tiene permisos de administrador
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Solo los administradores pueden usar este comando.", ephemeral=True)
            return

        if amount < 1 or amount > 100:
            await interaction.response.send_message("Debes indicar un número entre 1 y 100.", ephemeral=True)
            return

        deleted = await interaction.channel.purge(limit=amount)
        await interaction.response.send_message(f"🧹 Se han eliminado {len(deleted)} mensajes.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Purge(bot))