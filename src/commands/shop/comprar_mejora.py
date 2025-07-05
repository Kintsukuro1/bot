import discord
from discord.ext import commands
from discord import app_commands
from src.commands.shop.black_market_items import BLACK_MARKET  # Importamos directamente la lista de mejoras
from src.db import (
    get_balance, set_balance, ensure_user, registrar_transaccion, 
    agregar_item_usuario, usuario_tiene_item,
    get_user_items
)

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
        item = next((i for i in BLACK_MARKET if i["id"] == mejora_id), None)
        if not item:
            await interaction.response.send_message("❌ Mejora no encontrada.", ephemeral=True)
            return
        if balance < item["precio"]:
            await interaction.response.send_message("❌ No tienes suficiente saldo para comprar esta mejora.", ephemeral=True)
            return
        
        # Las mejoras permanentes tienen un ID especial: 1000 + item_id
        item_id_db = 1000 + item["id"]
        if usuario_tiene_item(user_id, item_id_db):
            await interaction.response.send_message("❌ Ya tienes esta mejora permanente.", ephemeral=True)
            return
            
        # Intentamos realizar la compra
        if not agregar_item_usuario(user_id, item_id_db, quantity=1):
            await interaction.response.send_message("❌ Error al procesar la compra. Tu saldo no ha sido afectado.", ephemeral=True)
            return
            
        # Si la compra fue exitosa, actualizamos el saldo y registramos la transacción
        set_balance(user_id, balance - item["precio"])
        # Crear descripción más corta para evitar el error de truncamiento
        item_id_corto = f"BM-{item['id']}"  # BM-1, BM-2, etc.
        registrar_transaccion(user_id, -item["precio"], f"Black Market: {item_id_corto}")
        embed = discord.Embed(
            title="✅ Mejora adquirida",
            description=f"¡Has comprado **{item['nombre']}**! {item['descripcion']}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ComprarMejora(bot))
    print("ComprarMejora cog loaded successfully.")
