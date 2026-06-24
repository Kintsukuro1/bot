import discord
from discord.ext import commands
from discord import app_commands

class Purge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="purge", description="Elimina una cantidad de mensajes del canal actual.")
    @app_commands.describe(amount="Cantidad de mensajes a eliminar (1-100)")
    @app_commands.default_permissions(administrator=True)
    async def purge(self, interaction: discord.Interaction, amount: int):
        if amount < 1 or amount > 100:
            await interaction.response.send_message("❌ Debes indicar un número entre 1 y 100.", ephemeral=True)
            return

        try:
            await interaction.response.defer(ephemeral=True)
            deleted = await interaction.channel.purge(limit=amount)
            
            embed = discord.Embed(
                title="🧹 Limpieza Completada",
                description=f"Se han eliminado **{len(deleted)}** mensajes exitosamente.",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Acción por: {interaction.user.display_name}")
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Error de Permisos",
                description="No tengo permisos suficientes para purgar mensajes en este canal.\nVerifica que tenga el permiso de `Administrar Mensajes`.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            raise
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error Inesperado",
                description=f"Ocurrió un error al intentar eliminar mensajes:\n```{e}```",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            raise

async def setup(bot):
    await bot.add_cog(Purge(bot))