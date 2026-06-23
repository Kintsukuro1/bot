import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from src.commands.shop.black_market_items import BLACK_MARKET  # Importamos directamente la lista de mejoras
from src.db import (
    get_balance, set_balance, ensure_user, registrar_transaccion, 
    agregar_item_usuario, usuario_tiene_item
)

def _procesar_compra_mejora(user_id, user_name, item):
    ensure_user(user_id, user_name)
    balance = get_balance(user_id)

    if balance < item["precio"]:
        return "no_balance", balance

    item_id_db = 1000 + item["id"]
    if usuario_tiene_item(user_id, item_id_db):
        return "already_owned", balance

    if not agregar_item_usuario(user_id, item_id_db, quantity=1):
        return "item_error", balance

    nuevo_balance = balance - item["precio"]
    set_balance(user_id, nuevo_balance)
    registrar_transaccion(user_id, -item["precio"], f"Black Market: BM-{item['id']}")
    return "ok", nuevo_balance

class ComprarMejora(commands.Cog):
    """Cog para comprar mejoras permanentes del black market."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="comprar_mejora", description="Compra una mejora permanente del black market por su ID.")
    @app_commands.describe(mejora_id="ID de la mejora a comprar")
    async def comprar_mejora(self, interaction: discord.Interaction, mejora_id: int):
        user_id = interaction.user.id
        user_name = interaction.user.name
        item = next((i for i in BLACK_MARKET if i["id"] == mejora_id), None)
        if not item:
            await interaction.response.send_message("❌ Mejora no encontrada.", ephemeral=True)
            return

        status, _balance = await asyncio.to_thread(
            _procesar_compra_mejora, user_id, user_name, item
        )

        if status == "no_balance":
            await interaction.response.send_message("❌ No tienes suficiente saldo para comprar esta mejora.", ephemeral=True)
            return

        if status == "already_owned":
            await interaction.response.send_message("❌ Ya tienes esta mejora permanente.", ephemeral=True)
            return

        if status == "item_error":
            await interaction.response.send_message("❌ Error al procesar la compra. Tu saldo no ha sido afectado.", ephemeral=True)
            return

        embed = discord.Embed(
            title="✅ Mejora adquirida",
            description=f"¡Has comprado **{item['nombre']}**! {item['descripcion']}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ComprarMejora(bot))
    print("ComprarMejora cog loaded successfully.")
