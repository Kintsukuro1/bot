import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from src.db import db_cursor, deduct_balance, add_balance, registrar_transaccion, get_user_items, usar_item_usuario, get_user_prestige_level

MERCADO_TAX = 0.05  # 5% de comisión (dinero destruido)

class UserMarket(commands.Cog):
    """Cog para la compra-venta directa de ítems entre usuarios."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="mercado", description="Muestra la lista de ítems publicados por otros usuarios en el mercado.")
    async def mercado(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        def _get_listings():
            with db_cursor() as c:
                c.execute("""
                    SELECT ListingID, SellerID, ItemID, Price, Currency, CreatedAt
                    FROM UserMarketListings
                    ORDER BY ListingID DESC
                    LIMIT 25
                """)
                return c.fetchall()
                
        listings = await asyncio.to_thread(_get_listings)
        
        embed = discord.Embed(
            title="🏪 Mercado de Usuarios (Venta Directa)",
            description="Ítems publicados por otros jugadores. La tienda retiene un 5% de comisión al vender.",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/3081/3081559.png")
        
        if not listings:
            embed.description = "No hay ítems publicados en este momento. ¡Sé el primero usando `/vender_item`!"
        else:
            from src.commands.shop.tienda import TIENDA_CATALOGO
            from src.commands.shop.black_market_items import BLACK_MARKET
            
            for list_id, seller_id, item_id, price, currency, created_at in listings:
                item_info = next((i for i in TIENDA_CATALOGO if i["id"] == item_id), None)
                if not item_info:
                    bm_id = item_id - 1000 if item_id >= 1000 else item_id
                    item_info = next((i for i in BLACK_MARKET if i["id"] == bm_id), None)
                    
                nombre = item_info["nombre"] if item_info else f"Ítem #{item_id}"
                moneda_icon = "🪙" if currency == "balance" else "🥉"
                
                embed.add_field(
                    name=f"📦 {nombre} — {price:,} {moneda_icon}",
                    value=f"`Publicación ID:` `{list_id}` | `Vendedor:` <@{seller_id}>",
                    inline=False
                )
                
        embed.set_footer(text="Usa /comprar_mercado <ID> para adquirir un ítem publicado.")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="vender_item", description="Publica un ítem de tu inventario en el Mercado de Usuarios.")
    @app_commands.describe(item_id="ID del ítem en tu inventario", precio="Precio de venta en Balance")
    async def vender_item(self, interaction: discord.Interaction, item_id: int, precio: int):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        
        if precio <= 0:
            await interaction.followup.send("❌ El precio debe ser un entero positivo.", ephemeral=True)
            return

        def _publish_listing():
            with db_cursor() as c:
                # Verificar prestigio para límite de publicaciones (Base: 2, Prestigio II+: 4)
                c.execute("SELECT COUNT(*) FROM UserMarketListings WHERE SellerID = %s", (user_id,))
                active_count = c.fetchone()[0]
                prestige = get_user_prestige_level(user_id)
                limit = 4 if prestige >= 2 else 2
                
                if active_count >= limit:
                    return False, f"Llegaste al límite de {limit} publicaciones simultáneas."
                
                # Consumir el ítem del inventario
                used = usar_item_usuario(user_id, item_id)
                if not used:
                    return False, "No posees este ítem en tu inventario o ya fue consumido."
                
                c.execute("""
                    INSERT INTO UserMarketListings (SellerID, ItemType, ItemID, Price, Currency)
                    VALUES (%s, 'item', %s, %s, 'balance')
                    RETURNING ListingID
                """, (user_id, item_id, precio))
                
                listing_id = c.fetchone()[0]
                return True, listing_id

        success, res = await asyncio.to_thread(_publish_listing)
        if success:
            await interaction.followup.send(f"✅ ¡Tu ítem ha sido publicado en el mercado con ID de publicación **`{res}`** por **{precio:,}** 🪙!", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {res}", ephemeral=True)

    @app_commands.command(name="comprar_mercado", description="Compra un ítem publicado en el mercado de usuarios.")
    @app_commands.describe(publicacion_id="ID de la publicación en el mercado")
    async def comprar_mercado(self, interaction: discord.Interaction, publicacion_id: int):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        
        def _buy_listing():
            with db_cursor() as c:
                c.execute("""
                    SELECT SellerID, ItemID, Price, Currency
                    FROM UserMarketListings
                    WHERE ListingID = %s
                """, (publicacion_id,))
                row = c.fetchone()
                if not row:
                    return False, "Publicación no encontrada o ya comprada."
                
                seller_id, item_id, price, currency = row
                if seller_id == user_id:
                    return False, "No puedes comprar tu propio ítem."
                
                # Cobrar al comprador
                c.execute("UPDATE Users SET Balance = Balance - %s WHERE UserID = %s AND Balance >= %s RETURNING Balance", (price, user_id, price))
                if not c.fetchone():
                    return False, "Saldo insuficiente para realizar esta compra."
                
                # Pagar al vendedor descontando el 5% de comisión (destruido)
                vendedor_pago = int(price * (1 - MERCADO_TAX))
                c.execute("UPDATE Users SET Balance = Balance + %s WHERE UserID = %s", (vendedor_pago, seller_id))
                
                # Transferir ítem al comprador
                from datetime import datetime, timedelta
                exp = datetime.now() + timedelta(days=3650)
                c.execute("INSERT INTO UserItems (UserID, ItemID, Quantity, Expiry, Used) VALUES (%s, %s, 1, %s, 0)", (user_id, item_id, exp))
                
                # Eliminar publicación
                c.execute("DELETE FROM UserMarketListings WHERE ListingID = %s", (publicacion_id,))
                
                return True, (seller_id, item_id, price, vendedor_pago)

        success, res = await asyncio.to_thread(_buy_listing)
        if success:
            seller_id, item_id, price, vendedor_pago = res
            await interaction.followup.send(f"✅ ¡Has comprado el ítem exitosamente por **{price:,}** 🪙!", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {res}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(UserMarket(bot))
    print("UserMarket cog loaded successfully.")
