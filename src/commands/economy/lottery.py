import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random

from src.db import get_balance, set_balance, ensure_user, registrar_transaccion
from src.db import get_lottery_tickets, buy_lottery_tickets, clear_lottery, get_lottery_pot

TICKET_PRICE = 100
BASE_POT = 5000

class Lottery(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    loteria_group = app_commands.Group(name="loteria", description="Comandos de la lotería del servidor")

    @loteria_group.command(name="info", description="Muestra la información del pozo actual de la lotería.")
    async def info(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        pot = await asyncio.to_thread(get_lottery_pot, TICKET_PRICE, BASE_POT)
        tickets = await asyncio.to_thread(get_lottery_tickets)
        
        my_tickets = tickets.count(interaction.user.id)
        total_tickets = len(tickets)
        win_chance = (my_tickets / total_tickets * 100) if total_tickets > 0 else 0.0

        embed = discord.Embed(
            title="🎟️ Lotería del Servidor 🎟️",
            description=f"¡Participa y gana en grande!\nCada ticket cuesta **{TICKET_PRICE}** monedas.",
            color=discord.Color.gold()
        )
        embed.add_field(name="💰 Pozo Actual", value=f"**{pot:,}** monedas", inline=False)
        embed.add_field(name="🎫 Tus Tickets", value=f"**{my_tickets}**", inline=True)
        embed.add_field(name="📊 Probabilidad de Ganar", value=f"**{win_chance:.2f}%**", inline=True)
        embed.add_field(name="Total de Tickets", value=f"**{total_tickets}**", inline=True)
        
        await interaction.followup.send(embed=embed)

    @loteria_group.command(name="comprar", description="Compra tickets para la lotería del servidor.")
    @app_commands.describe(cantidad="Cuántos tickets quieres comprar")
    async def comprar(self, interaction: discord.Interaction, cantidad: int):
        if cantidad <= 0:
            await interaction.response.send_message("❌ Debes comprar al menos 1 ticket.", ephemeral=True)
            return
            
        if cantidad > 100:
            await interaction.response.send_message("❌ Solo puedes comprar un máximo de 100 tickets a la vez para evitar monopolios.", ephemeral=True)
            return

        costo_total = cantidad * TICKET_PRICE
        user_id = interaction.user.id
        
        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)
        saldo = await asyncio.to_thread(get_balance, user_id)
        
        if saldo < costo_total:
            await interaction.response.send_message(f"❌ No tienes suficiente saldo. Necesitas **{costo_total}** monedas para {cantidad} tickets.", ephemeral=True)
            return

        await interaction.response.defer()
        
        # Cobrar y dar tickets
        await asyncio.to_thread(set_balance, user_id, saldo - costo_total)
        await asyncio.to_thread(registrar_transaccion, user_id, -costo_total, f"Compra {cantidad} tickets de lotería")
        await asyncio.to_thread(buy_lottery_tickets, user_id, cantidad)
        
        pot = await asyncio.to_thread(get_lottery_pot, TICKET_PRICE, BASE_POT)

        embed = discord.Embed(
            title="🎫 ¡Compra Exitosa!",
            description=f"Has comprado **{cantidad}** tickets por **{costo_total}** monedas.\n\n¡El pozo ha subido a **{pot:,}** monedas!\n\nTe deseamos mucha suerte en el próximo sorteo 🍀",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed)

    @loteria_group.command(name="sortear", description="Realiza el sorteo de la lotería (Solo Admins).")
    @app_commands.default_permissions(administrator=True)
    async def sortear(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        tickets = await asyncio.to_thread(get_lottery_tickets)
        pot = await asyncio.to_thread(get_lottery_pot, TICKET_PRICE, BASE_POT)
        
        if not tickets:
            await interaction.followup.send("❌ No se puede realizar el sorteo porque nadie ha comprado tickets.")
            return

        # Elegir ganador aleatoriamente de la piscina de tickets (si tienes 10 tickets, tienes 10 entradas en la lista)
        ganador_id = random.choice(tickets)
        
        # Entregar premio
        await asyncio.to_thread(ensure_user, ganador_id)
        saldo_ganador = await asyncio.to_thread(get_balance, ganador_id)
        await asyncio.to_thread(set_balance, ganador_id, saldo_ganador + pot)
        await asyncio.to_thread(registrar_transaccion, ganador_id, pot, f"¡GANADOR DE LA LOTERÍA! ({len(tickets)} tickets totales)")
        
        # Limpiar lotería
        await asyncio.to_thread(clear_lottery)
        
        # Intentar mencionar al ganador
        ganador_member = interaction.guild.get_member(ganador_id)
        mencion = ganador_member.mention if ganador_member else f"<@{ganador_id}>"
        
        embed = discord.Embed(
            title="🎉 ¡SORTEO DE LA LOTERÍA! 🎉",
            description=f"¡El gran ganador de esta edición ha sido elegido!\n\n👑 **Ganador:** {mencion}\n💰 **Premio total:** {pot:,} monedas\n🎟️ **Tickets totales vendidos:** {len(tickets)}",
            color=discord.Color.gold()
        )
        embed.set_footer(text="¡Una nueva lotería ha comenzado! Usa /loteria comprar para participar.")
        
        await interaction.followup.send(content=f"¡Felicidades {mencion}!", embed=embed)

async def setup(bot):
    await bot.add_cog(Lottery(bot))
    print("Lottery cog cargado con éxito.")
