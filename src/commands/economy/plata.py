import discord
from discord.ext import commands
from discord import app_commands
from src.db import get_balance, ensure_user

class Plata(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="plata", description="Consulta tu balance o el de otro usuario.")
    @app_commands.describe(usuario="Usuario a consultar (opcional)")
    async def plata(self, interaction: discord.Interaction, usuario: discord.Member = None):
        if usuario:
            ensure_user(usuario.id, usuario.name)
            balance = get_balance(usuario.id)
            nombre = usuario.display_name
        else:
            ensure_user(interaction.user.id, interaction.user.name)
            balance = get_balance(interaction.user.id)
            nombre = interaction.user.display_name
        embed = discord.Embed(
            title=f"💰 Balance de {nombre}",
            description=f"Saldo actual: **{balance}** monedas",
            color=discord.Color.gold()
        )
        if usuario:
            embed.set_thumbnail(url=usuario.display_avatar.url)
        else:
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"Solicitado por {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Plata(bot))
    print("Plata cog loaded successfully.")
