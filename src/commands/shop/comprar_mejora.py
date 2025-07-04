import discord
from discord.ext import commands
from discord import app_commands
from src.db import get_balance, set_balance, ensure_user, registrar_transaccion, agregar_item_usuario, usuario_tiene_item, get_black_market_items

class ComprarMejora(commands.Cog):
    """Cog para comprar mejoras permanentes del black market."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="comprar_mejora", description="Compra una mejora permanente del black market por su ID.")
    @app_commands.describe(mejora_id="ID de la mejora a comprar")
    async def comprar_mejora(self, interaction: discord.Interaction, mejora_id: int):
        user_id = interaction.user.id
        user_name = interaction.user.name
        ensure_user(user_id, user_name)
        balance = get_balance(user_id)
        items = get_black_market_items()
        item = next((i for i in items if i["id"] == mejora_id), None)
        if not item:
            await interaction.response.send_message("❌ Mejora no encontrada.", ephemeral=True)
            return
        if balance < item["precio"]:
            await interaction.response.send_message("❌ No tienes suficiente saldo para comprar esta mejora.", ephemeral=True)
            return
        if usuario_tiene_item(user_id, 1000 + item["id"]):
            await interaction.response.send_message("❌ Ya tienes esta mejora permanente.", ephemeral=True)
            return
        set_balance(user_id, balance - item["precio"])
        registrar_transaccion(user_id, -item["precio"], f"Compra blackmarket: {item['nombre']}")
        agregar_item_usuario(user_id, 1000 + item["id"], cantidad=1)
        embed = discord.Embed(
            title="✅ Mejora adquirida",
            description=f"¡Has comprado **{item['nombre']}**! {item['descripcion']}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ComprarMejora(bot))
    print("ComprarMejora cog loaded successfully.")
