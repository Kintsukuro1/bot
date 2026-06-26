import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from src.db import get_balance, ensure_user

def _get_user_balance(user_id, user_name):
    ensure_user(user_id, user_name)
    return get_balance(user_id)

class Plata(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="plata", description="Consulta tu balance o el de otro usuario.")
    @app_commands.describe(usuario="Usuario a consultar (opcional)")
    async def plata(self, interaction: discord.Interaction, usuario: discord.Member = None):
        await interaction.response.defer()
        if usuario:
            balance = await asyncio.to_thread(_get_user_balance, usuario.id, usuario.name)
            nombre = usuario.display_name
        else:
            balance = await asyncio.to_thread(
                _get_user_balance, interaction.user.id, interaction.user.name
            )
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
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Plata(bot))
    print("Plata cog loaded successfully.")
