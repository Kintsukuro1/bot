import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
from src.db import db_cursor, deduct_balance, add_balance, usar_item_usuario, get_user_items

AUCTION_TAX = 0.08  # 8% comisión destruida al ganar subasta

class AuctionBidModal(discord.ui.Modal, title="💰 Realizar Puja"):
    monto = discord.ui.TextInput(label="Monto de tu puja (Balance)", placeholder="Ej. 50000", required=True)

    def __init__(self, auction_id: int):
        super().__init__()
        self.auction_id = auction_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bid_val = int(self.monto.value)
        except ValueError:
            await interaction.response.send_message("❌ Ingresa un valor numérico válido.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

        def _place_bid():
            with db_cursor() as c:
                c.execute("""
                    SELECT SellerID, CurrentBid, HighestBidderID, AuctionEndTime
                    FROM UserAuctions
                    WHERE AuctionID = %s
                """, (self.auction_id,))
                row = c.fetchone()
                if not row:
                    return False, "Subasta no encontrada o finalizada."

                seller_id, current_bid, prev_bidder, end_time = row
                if seller_id == user_id:
                    return False, "No puedes pujar en tu propia subasta."

                if bid_val <= current_bid:
                    return False, f"Tu puja debe ser mayor a la puja actual ({current_bid:,} 🪙)."

                now = datetime.now()
                if now >= end_time:
                    return False, "Esta subasta ya finalizó."

                # Descontar Balance del nuevo postor
                c.execute("UPDATE Users SET Balance = Balance - %s WHERE UserID = %s AND Balance >= %s RETURNING Balance", (bid_val, user_id, bid_val))
                if not c.fetchone():
                    return False, "No tienes suficiente saldo para esta puja."

                # Reembolsar al postor anterior
                if prev_bidder:
                    c.execute("UPDATE Users SET Balance = Balance + %s WHERE UserID = %s", (current_bid, prev_bidder))

                # Protección Anti-Sniping: Extender 3 min si faltan <2 min
                new_end = end_time
                if (end_time - now).total_seconds() < 120:
                    new_end = now + timedelta(minutes=3)

                c.execute("""
                    UPDATE UserAuctions
                    SET CurrentBid = %s, HighestBidderID = %s, AuctionEndTime = %s
                    WHERE AuctionID = %s
                """, (bid_val, user_id, new_end, self.auction_id))

                return True, (bid_val, new_end)

        success, res = await asyncio.to_thread(_place_bid)
        if success:
            bid_val, new_end = res
            await interaction.followup.send(f"✅ ¡Tu puja de **{bid_val:,}** 🪙 fue registrada con éxito!", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {res}", ephemeral=True)

class AuctionBidButtonView(discord.ui.View):
    def __init__(self, auction_id: int):
        super().__init__(timeout=None)
        self.auction_id = auction_id

    @discord.ui.button(label="💰 Pujar", style=discord.ButtonStyle.success, custom_id="btn_auction_bid")
    async def btn_bid(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AuctionBidModal(self.auction_id))

class Auctions(commands.Cog):
    """Cog para el sistema de subastas con canal en vivo y anti-sniping."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="configurar_subastas", description="[ADMIN] Configura el canal donde se publicarán las subastas en vivo.")
    @app_commands.checks.has_permissions(administrator=True)
    async def configurar_subastas(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        
        def _set_channel():
            with db_cursor() as c:
                c.execute("""
                    INSERT INTO GuildConfig (GuildID, AuctionChannelID)
                    VALUES (%s, %s)
                    ON CONFLICT (GuildID) DO UPDATE SET AuctionChannelID = EXCLUDED.AuctionChannelID
                """, (interaction.guild_id, canal.id))
        await asyncio.to_thread(_set_channel)
        await interaction.followup.send(f"✅ Canal de subastas configurado en {canal.mention}.", ephemeral=True)

    @app_commands.command(name="subastar_item", description="Inicia una subasta para un ítem de tu inventario (4h, 8h o 12h).")
    @app_commands.describe(item_id="ID del ítem en tu inventario", precio_inicial="Precio base de la puja", duracion_horas="Duración (4, 8 o 12 horas)")
    @app_commands.choices(duracion_horas=[
        app_commands.Choice(name="4 Horas", value=4),
        app_commands.Choice(name="8 Horas", value=8),
        app_commands.Choice(name="12 Horas", value=12)
    ])
    async def subastar_item(self, interaction: discord.Interaction, item_id: int, precio_inicial: int, duracion_horas: int):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        
        if precio_inicial <= 0:
            await interaction.followup.send("❌ El precio inicial debe ser positivo.", ephemeral=True)
            return

        def _create_auction():
            with db_cursor() as c:
                used = usar_item_usuario(user_id, item_id)
                if not used:
                    return False, "No tienes este ítem en tu inventario."

                end_time = datetime.now() + timedelta(hours=duracion_horas)
                c.execute("""
                    INSERT INTO UserAuctions (SellerID, ItemType, ItemID, CurrentBid, AuctionEndTime, Currency)
                    VALUES (%s, 'item', %s, %s, %s, 'balance')
                    RETURNING AuctionID
                """, (user_id, item_id, precio_inicial, end_time))
                
                auction_id = c.fetchone()[0]
                
                # Obtener canal configurado
                c.execute("SELECT AuctionChannelID FROM GuildConfig WHERE GuildID = %s", (interaction.guild_id,))
                row = c.fetchone()
                ch_id = row[0] if row else None
                return True, (auction_id, end_time, ch_id)

        success, res = await asyncio.to_thread(_create_auction)
        if not success:
            await interaction.followup.send(f"❌ {res}", ephemeral=True)
            return

        auction_id, end_time, ch_id = res
        await interaction.followup.send(f"🔨 ¡Subasta #{auction_id} creada exitosamente!", ephemeral=True)

        # Si hay canal de subastas configurado, publicar el mensaje interactivo
        if ch_id:
            channel = interaction.guild.get_channel(ch_id)
            if channel:
                from src.commands.shop.tienda import TIENDA_CATALOGO
                item_info = next((i for i in TIENDA_CATALOGO if i["id"] == item_id), None)
                nombre = item_info["nombre"] if item_info else f"Ítem #{item_id}"
                
                embed = discord.Embed(
                    title=f"🔨 ¡Nueva Subasta #{auction_id}!",
                    description=f"**Objeto:** {nombre}\n**Vendedor:** <@{user_id}>\n**Puja Inicial:** {precio_inicial:,} 🪙\n**Finaliza en:** <t:{int(end_time.timestamp())}:R>",
                    color=discord.Color.gold()
                )
                view = AuctionBidButtonView(auction_id)
                await channel.send(embed=embed, view=view)

    @app_commands.command(name="pujar", description="Puja en una subasta activa.")
    @app_commands.describe(subasta_id="ID de la subasta", monto="Monto a pujar")
    async def pujar(self, interaction: discord.Interaction, subasta_id: int, monto: int):
        modal = AuctionBidModal(subasta_id)
        modal.monto.default = str(monto)
        await interaction.response.send_modal(modal)

async def setup(bot):
    await bot.add_cog(Auctions(bot))
    print("Auctions cog loaded successfully.")
