import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
from src.db import db_cursor, deduct_balance, add_balance, registrar_transaccion, get_user_items, usar_item_usuario, get_user_prestige_level

MERCADO_TAX = 0.05  # 5% de comisión (dinero destruido)

class UserMarket(commands.Cog):
    """Cog para la compra-venta directa de ítems, mascotas y equipo entre usuarios."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="mercado", description="Muestra la lista de publicaciones activas en el mercado de usuarios.")
    async def mercado(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        def _get_listings():
            with db_cursor() as c:
                c.execute("""
                    SELECT ListingID, SellerID, ItemType, ItemID, Price, Currency, CreatedAt
                    FROM UserMarketListings
                    ORDER BY ListingID DESC
                    LIMIT 25
                """)
                rows = c.fetchall()
                
                result = []
                for list_id, seller_id, item_type, item_id, price, currency, created_at in rows:
                    name_str = f"Objeto #{item_id}"
                    if item_type == 'item':
                        from src.commands.shop.tienda import TIENDA_CATALOGO
                        from src.commands.shop.black_market_items import BLACK_MARKET
                        item_info = next((i for i in TIENDA_CATALOGO if i["id"] == item_id), None)
                        if not item_info:
                            bm_id = item_id - 1000 if item_id >= 1000 else item_id
                            item_info = next((i for i in BLACK_MARKET if i["id"] == bm_id), None)
                        name_str = f"📦 {item_info['nombre']}" if item_info else f"📦 Ítem #{item_id}"

                    elif item_type == 'pet':
                        c.execute("""
                            SELECT p.Emoji, p.Name, p.Rarity, up.Level, up.Nickname
                            FROM UserPets up JOIN PetsCatalog p ON up.PetID = p.PetID
                            WHERE up.UserPetID = %s
                        """, (item_id,))
                        p_row = c.fetchone()
                        if p_row:
                            p_emoji, p_name, p_rarity, p_lvl, p_nick = p_row
                            display_n = p_nick if p_nick and p_nick.strip() else p_name
                            name_str = f"🐾 {p_emoji} **{display_n}** (Nv. {p_lvl} | {p_rarity})"
                        else:
                            name_str = f"🐾 Mascota #{item_id}"

                    elif item_type == 'equipment':
                        c.execute("""
                            SELECT ItemName, Rarity, ItemLevel, Slot, PrimaryStat, PrimaryValue
                            FROM UserEquipment WHERE ID = %s
                        """, (item_id,))
                        eq_row = c.fetchone()
                        if eq_row:
                            eq_name, eq_rarity, eq_lvl, eq_slot, eq_pstat, eq_pval = eq_row
                            name_str = f"🛡️ **{eq_name}** ({eq_rarity} Nv.{eq_lvl} {eq_slot.capitalize()})"
                        else:
                            name_str = f"🛡️ Equipo #{item_id}"

                    result.append((list_id, seller_id, item_type, name_str, price, currency))
                return result

        listings = await asyncio.to_thread(_get_listings)
        
        embed = discord.Embed(
            title="🏪 Mercado de Usuarios (Venta Directa)",
            description="Ítems, Mascotas y Equipos publicados por otros jugadores. La tienda retiene un **5%** de comisión al vender.",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/3081/3081559.png")
        
        if not listings:
            embed.description = "No hay publicaciones activas en este momento. ¡Sé el primero usando `/vender_item`, `/vender_mascota` o `/vender_equipo`!"
        else:
            for list_id, seller_id, item_type, name_str, price, currency in listings:
                moneda_icon = "🪙" if currency == "balance" else "🥉"
                embed.add_field(
                    name=f"{name_str} — {price:,} {moneda_icon}",
                    value=f"`Publicación ID:` `{list_id}` | `Tipo:` `{item_type.upper()}` | `Vendedor:` <@{seller_id}>",
                    inline=False
                )
                
        embed.set_footer(text="Usa /comprar_mercado <ID> para adquirir cualquier publicación.")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="vender_item", description="Publica un ítem consumible de tu inventario en el Mercado.")
    @app_commands.describe(item_id="ID del ítem en tu inventario", precio="Precio de venta en Balance")
    async def vender_item(self, interaction: discord.Interaction, item_id: int, precio: int):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        
        if precio <= 0:
            await interaction.followup.send("❌ El precio debe ser un entero positivo.", ephemeral=True)
            return

        def _publish():
            with db_cursor() as c:
                c.execute("SELECT COUNT(*) FROM UserMarketListings WHERE SellerID = %s", (user_id,))
                active_count = c.fetchone()[0]
                prestige = get_user_prestige_level(user_id)
                limit = 4 if prestige >= 2 else 2
                
                if active_count >= limit:
                    return False, f"Llegaste al límite de {limit} publicaciones simultáneas."
                
                used = usar_item_usuario(user_id, item_id)
                if not used:
                    return False, "No posees este ítem en tu inventario o ya fue consumido."
                
                c.execute("""
                    INSERT INTO UserMarketListings (SellerID, ItemType, ItemID, Price, Currency)
                    VALUES (%s, 'item', %s, %s, 'balance')
                    RETURNING ListingID
                """, (user_id, item_id, precio))
                return True, c.fetchone()[0]

        success, res = await asyncio.to_thread(_publish)
        if success:
            await interaction.followup.send(f"✅ ¡Ítem publicado en el mercado con ID **`{res}`** por **{precio:,}** 🪙!", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {res}", ephemeral=True)

    @app_commands.command(name="vender_mascota", description="Publica una mascota de tu colección en el Mercado.")
    @app_commands.describe(pet_id="ID de la mascota (UserPetID)", precio="Precio de venta en Balance")
    async def vender_mascota(self, interaction: discord.Interaction, pet_id: int, precio: int):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        
        if precio <= 0:
            await interaction.followup.send("❌ El precio debe ser un entero positivo.", ephemeral=True)
            return

        def _publish_pet():
            with db_cursor() as c:
                c.execute("SELECT COUNT(*) FROM UserMarketListings WHERE SellerID = %s", (user_id,))
                if c.fetchone()[0] >= (4 if get_user_prestige_level(user_id) >= 2 else 2):
                    return False, "Llegaste al límite de publicaciones simultáneas."
                
                c.execute("SELECT UserPetID FROM UserPets WHERE UserPetID = %s AND UserID = %s AND Status != 'Escapó'", (pet_id, user_id))
                if not c.fetchone():
                    return False, "No posees esa mascota en tu colección."
                
                c.execute("UPDATE UserPets SET EquippedSlot = NULL, Status = 'En Mercado' WHERE UserPetID = %s", (pet_id,))
                c.execute("""
                    INSERT INTO UserMarketListings (SellerID, ItemType, ItemID, Price, Currency)
                    VALUES (%s, 'pet', %s, %s, 'balance')
                    RETURNING ListingID
                """, (user_id, pet_id, precio))
                return True, c.fetchone()[0]

        success, res = await asyncio.to_thread(_publish_pet)
        if success:
            await interaction.followup.send(f"🐾 ¡Mascota ID `{pet_id}` publicada en el mercado con ID **`{res}`** por **{precio:,}** 🪙!", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {res}", ephemeral=True)

    @app_commands.command(name="vender_equipo", description="Publica una pieza de equipo/arma de tu inventario en el Mercado.")
    @app_commands.describe(equipo_id="ID de la pieza de equipo", precio="Precio de venta en Balance")
    async def vender_equipo(self, interaction: discord.Interaction, equipo_id: int, precio: int):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        
        if precio <= 0:
            await interaction.followup.send("❌ El precio debe ser un entero positivo.", ephemeral=True)
            return

        def _publish_eq():
            with db_cursor() as c:
                c.execute("SELECT COUNT(*) FROM UserMarketListings WHERE SellerID = %s", (user_id,))
                if c.fetchone()[0] >= (4 if get_user_prestige_level(user_id) >= 2 else 2):
                    return False, "Llegaste al límite de publicaciones simultáneas."
                
                c.execute("SELECT ID, Slot FROM UserEquipment WHERE ID = %s AND UserID = %s", (equipo_id, user_id))
                row = c.fetchone()
                if not row:
                    return False, "No posees esa pieza de equipo."
                
                c.execute("UPDATE UserEquipment SET Slot = 'mercado', UserID = 0 WHERE ID = %s", (equipo_id,))
                c.execute("""
                    INSERT INTO UserMarketListings (SellerID, ItemType, ItemID, Price, Currency)
                    VALUES (%s, 'equipment', %s, %s, 'balance')
                    RETURNING ListingID
                """, (user_id, equipo_id, precio))
                return True, c.fetchone()[0]

        success, res = await asyncio.to_thread(_publish_eq)
        if success:
            await interaction.followup.send(f"🛡️ ¡Pieza de equipo publicada en el mercado con ID **`{res}`** por **{precio:,}** 🪙!", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {res}", ephemeral=True)

    @app_commands.command(name="comprar_mercado", description="Compra una publicación activa del mercado de usuarios.")
    @app_commands.describe(publicacion_id="ID de la publicación en el mercado")
    async def comprar_mercado(self, interaction: discord.Interaction, publicacion_id: int):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        
        def _buy():
            with db_cursor() as c:
                c.execute("""
                    SELECT SellerID, ItemType, ItemID, Price, Currency
                    FROM UserMarketListings WHERE ListingID = %s
                """, (publicacion_id,))
                row = c.fetchone()
                if not row:
                    return False, "Publicación no encontrada o ya vendida."
                
                seller_id, item_type, item_id, price, currency = row
                if seller_id == user_id:
                    return False, "No puedes comprar tu propia publicación."
                
                c.execute("UPDATE Users SET Balance = Balance - %s WHERE UserID = %s AND Balance >= %s RETURNING Balance", (price, user_id, price))
                if not c.fetchone():
                    return False, "Saldo insuficiente para realizar esta compra."
                
                pago_vendedor = int(price * (1 - MERCADO_TAX))
                c.execute("UPDATE Users SET Balance = Balance + %s WHERE UserID = %s", (pago_vendedor, seller_id))
                
                if item_type == 'item':
                    exp = datetime.now() + timedelta(days=3650)
                    c.execute("INSERT INTO UserItems (UserID, ItemID, Quantity, Expiry, Used) VALUES (%s, %s, 1, %s, 0)", (user_id, item_id, exp))
                elif item_type == 'pet':
                    c.execute("UPDATE UserPets SET UserID = %s, Status = 'Activo', EquippedSlot = NULL WHERE UserPetID = %s", (user_id, item_id))
                elif item_type == 'equipment':
                    c.execute("UPDATE UserEquipment SET UserID = %s, Slot = 'Inventario' WHERE ID = %s", (user_id, item_id))
                
                c.execute("DELETE FROM UserMarketListings WHERE ListingID = %s", (publicacion_id,))
                return True, (seller_id, item_type, price, pago_vendedor)

        success, res = await asyncio.to_thread(_buy)
        if success:
            seller_id, item_type, price, pago_vendedor = res
            await interaction.followup.send(f"✅ ¡Has comprado la publicación exitosamente por **{price:,}** 🪙! El vendedor recibió **{pago_vendedor:,}** 🪙 (tras 5% comisión).", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {res}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(UserMarket(bot))
    print("UserMarket cog loaded successfully.")
