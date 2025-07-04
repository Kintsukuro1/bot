import discord
from discord.ext import commands
from discord import app_commands
from src.db import get_balance, ensure_user

class Historial(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="historial", description="Muestra el historial de transacciones del usuario.")
    @app_commands.describe(usuario="Usuario a consultar (opcional)")
    async def historial(self, interaction: discord.Interaction, usuario: discord.Member = None):
        # Placeholder para la implementación real
        target_user = usuario or interaction.user
        ensure_user(target_user.id, target_user.display_name)
        
        embed = discord.Embed(
            title=f"📜 Historial de {target_user.display_name}",
            description="Esta funcionalidad será implementada próximamente.",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Solicitado por {interaction.user.display_name}")
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Historial(bot))
    print("Historial cog loaded successfully.")
