import discord
import random
import asyncio
from src.db import get_user_equipment, insert_gem_discounted, get_gem_catalog, get_consumable_catalog, buy_consumable_discounted
from src.utils.combat_progression import SLOT_EMOJIS, format_currency

class PhantomMerchantSlotSelectView(discord.ui.View):
    """Vista efímera para seleccionar el slot donde insertar una gema comprada al Mercader Fantasma."""

    def __init__(self, buyer: discord.Member, gem_key: str, gem_name: str, discounted_price: int, equipment: dict):
        super().__init__(timeout=60)
        self.buyer = buyer
        self.gem_key = gem_key
        self.gem_name = gem_name
        self.discounted_price = discounted_price
        self.equipment = equipment

        # Filtrar slots válidos que tienen equipo para insertar
        options = []
        valid_slots = ["Cabeza", "Hombros", "Pecho", "Pantalones", "Guantes", "Botas", "Anillo", "Amuleto", "Arma", "Escudo"]
        for slot in valid_slots:
            piece = equipment.get(slot)
            if not piece:
                continue
            
            piece_name = piece.get("name", "Desconocido")
            gem_text = ""
            if piece and piece.get("gem"):
                gem_text = f" (💎 {piece['gem']['name']})"
            options.append(
                discord.SelectOption(
                    label=f"{SLOT_EMOJIS.get(slot, '🔹')} {slot}",
                    value=slot,
                    description=f"Equipo: {piece_name}{gem_text}"
                )
            )
            
        self.slot_select = discord.ui.Select(
            placeholder=f"Elegir slot para {gem_name}...",
            options=options,
            min_values=1,
            max_values=1,
        )
        self.slot_select.callback = self.slot_callback
        self.add_item(self.slot_select)

    async def slot_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.buyer.id:
            await interaction.response.send_message("❌ Esta opción no es para ti.", ephemeral=True)
            return

        slot = self.slot_select.values[0]
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        success, message = await asyncio.to_thread(
            insert_gem_discounted, self.buyer.id, slot, self.gem_key, self.discounted_price
        )
        if success:
            embed = discord.Embed(
                title="✅ Compra Exitosa",
                description=message,
                color=discord.Color.green()
            )
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.followup.send(f"❌ Error: {message}", ephemeral=True)


class PhantomMerchantView(discord.ui.View):
    """Vista de la tienda del Mercader Fantasma en raids."""

    def __init__(self, participants: list[discord.Member], cog):
        super().__init__(timeout=60)
        self.participants = participants
        self.cog = cog
        self.message: discord.Message | None = None
        self.offers = self._roll_offers()
        self._build_interface()

    def _roll_offers(self):
        gems = get_gem_catalog()
        consumables = get_consumable_catalog()
        pool = [{"kind": "gem", **g} for g in gems] + [{"kind": "consumable", **c} for c in consumables]
        
        # Roll 4 distinct offers
        chosen = random.sample(pool, min(4, len(pool)))
        discount = random.uniform(0.20, 0.30)
        
        for offer in chosen:
            price = offer.get("price") or offer.get("Price") or 0
            offer["original_price"] = price
            offer["discounted_price"] = int(price * (1 - discount))
            
        return chosen

    def _build_interface(self):
        options = []
        for idx, offer in enumerate(self.offers):
            kind = offer["kind"]
            name = offer["name"]
            orig_price = offer["original_price"]
            disc_price = offer["discounted_price"]
            
            orig_price_str = f"~~{orig_price}~~"
            disc_price_str = f"{disc_price} Bronce"
            
            if kind == "gem":
                val_str = f"+{int(offer['bonus_value'])}" if not offer["is_percentage"] else f"+{int(offer['bonus_value'] * 100)}%"
                desc = f"💎 Gema · {offer['stat_target'].upper()} {val_str} · {orig_price_str} -> {disc_price_str}"
            else:
                desc = f"🧪 Consumible · {offer['description'][:45]}... · {orig_price_str} -> {disc_price_str}"

            options.append(
                discord.SelectOption(
                    label=name,
                    value=str(idx),
                    description=desc
                )
            )

        self.shop_select = discord.ui.Select(
            placeholder="🛒 Selecciona un trato de la tienda...",
            options=options,
            min_values=1,
            max_values=1
        )
        self.shop_select.callback = self.shop_callback
        self.add_item(self.shop_select)

    def _build_embed(self):
        embed = discord.Embed(
            title="🛒 El Mercader Fantasma ha Aparecido",
            description=(
                "*Una figura encapuchada que aparece entre la niebla, ofreciendo tratos... por un precio.*\n\n"
                "**Ofertas del Día (20-30% de Descuento):**\n"
            ),
            color=0x4B0082  # Dark indigo / spectral color
        )
        
        for offer in self.offers:
            kind = offer["kind"]
            name = offer["name"]
            orig_price = offer["original_price"]
            disc_price = offer["discounted_price"]
            
            orig_price_formatted = format_currency(orig_price)
            disc_price_formatted = format_currency(disc_price)
            
            if kind == "gem":
                val_str = f"+{int(offer['bonus_value'])}" if not offer["is_percentage"] else f"+{int(offer['bonus_value'] * 100)}%"
                details = f"Efecto: **+{offer['stat_target'].upper()} {val_str}**"
            else:
                details = f"Efecto: *{offer['description']}*"

            embed.add_field(
                name=f"✨ {name}",
                value=f"{details}\nPrecio: ~~{orig_price_formatted}~~ **{disc_price_formatted}**",
                inline=False
            )
            
        embed.set_footer(text=f"Tienda disponible por 60 segundos · Solo participantes de la raid pueden comprar.")
        return embed

    async def shop_callback(self, interaction: discord.Interaction):
        # Validate participant
        buyer_ids = [p.id for p in self.participants]
        if interaction.user.id not in buyer_ids:
            await interaction.response.send_message("❌ No formas parte de este grupo. No puedes comprar aquí.", ephemeral=True)
            return

        idx = int(self.shop_select.values[0])
        offer = self.offers[idx]
        kind = offer["kind"]
        disc_price = offer["discounted_price"]
        item_name = offer["name"]
        
        if kind == "consumable":
            # Direct purchase
            await interaction.response.defer(ephemeral=True)
            success, message = await asyncio.to_thread(
                buy_consumable_discounted, interaction.user.id, offer["consumable_key"], disc_price
            )
            if success:
                embed = discord.Embed(
                    title="✅ Compra Exitosa",
                    description=message,
                    color=discord.Color.green()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Error: {message}", ephemeral=True)
        else:
            # Gem: requires slot selection
            await interaction.response.defer(ephemeral=True)
            equipment = await asyncio.to_thread(get_user_equipment, interaction.user.id)
            view = PhantomMerchantSlotSelectView(
                buyer=interaction.user,
                gem_key=offer["gem_key"],
                gem_name=item_name,
                discounted_price=disc_price,
                equipment=equipment
            )
            embed = discord.Embed(
                title="💎 Ranura de Inserción",
                description=f"Selecciona en qué pieza de tu equipo deseas insertar **{item_name}** por **{format_currency(disc_price)}**:",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        
        # Clean up all participants from active_raids
        for p in self.participants:
            self.cog.active_raids.discard(p.id)

        if self.message:
            try:
                embed = self.message.embeds[0]
                embed.description = "⏰ *La tienda del Mercader Fantasma ha desaparecido en la niebla...*\n\n" + embed.description
                embed.color = discord.Color.dark_gray()
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass
