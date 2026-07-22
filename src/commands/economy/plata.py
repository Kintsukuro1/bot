import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from src.db import get_balance, ensure_user, add_balance, registrar_transaccion
from src.utils.prestige_config import format_username_with_prestige

def _get_user_balance_info(user_id, user_name):
    ensure_user(user_id, user_name)
    from src.db import get_bank_balance
    return get_balance(user_id), get_bank_balance(user_id)

def _crear_plata_db(user_id, user_name, cantidad):
    ensure_user(user_id, user_name)
    add_balance(user_id, cantidad)
    registrar_transaccion(user_id, cantidad, "Generación Administrativa de Plata")
    return get_balance(user_id)

class Plata(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="plata", description="Consulta tu balance o el de otro usuario.")
    @app_commands.describe(usuario="Usuario a consultar (opcional)")
    async def plata(self, interaction: discord.Interaction, usuario: discord.Member = None):
        await interaction.response.defer()
        target_user = usuario or interaction.user
        
        cash, bank = await asyncio.to_thread(
            _get_user_balance_info, target_user.id, target_user.name
        )
        nombre = await asyncio.to_thread(format_username_with_prestige, target_user.id, target_user.display_name)
        
        embed = discord.Embed(
            title=f"💰 Dinero de {nombre}",
            color=discord.Color.gold()
        )
        embed.add_field(name="💵 En Mano", value=f"**{cash:,}** monedas", inline=True)
        embed.add_field(name="🏦 En Banco", value=f"**{bank:,}** monedas", inline=True)
        embed.add_field(name="📊 Total", value=f"**{cash + bank:,}** monedas", inline=False)
        
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.set_footer(text=f"Solicitado por {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="crear_plata", description="Genera dinero por si se buguean cosas (Solo Administrador).")
    @app_commands.describe(cantidad="Cantidad de dinero a generar", usuario="Usuario que recibirá el dinero (opcional)")
    async def crear_plata(self, interaction: discord.Interaction, cantidad: int, usuario: discord.Member = None):
        if interaction.user.id != 287396390747766795:
            await interaction.response.send_message("❌ No tienes permisos para usar este comando.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        target = usuario or interaction.user
        
        nuevo_saldo = await asyncio.to_thread(
            _crear_plata_db, target.id, target.name, cantidad
        )
        
        embed = discord.Embed(
            title="🛠️ Comando de Soporte: Generar Plata",
            description=f"Se han generado **{cantidad}** monedas para {target.mention}.\nNuevo saldo: **{nuevo_saldo}** monedas.",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Operación realizada por {interaction.user.display_name}")
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Plata(bot))
