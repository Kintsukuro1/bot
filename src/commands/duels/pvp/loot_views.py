import discord
import asyncio
from src.db import (
    equip_item, calc_sell_price, add_balance, registrar_transaccion,
    get_user_equipment, get_gem_catalog, insert_gem, remove_gem,
    add_combat_currency, format_currency, buy_consumable, get_combat_stats
)
from src.utils.combat_progression import (
    format_item_stats_display, ALL_STATS, format_stat_type, SLOT_EMOJIS,
    LOOT_TIMEOUT_SECONDS, EQUIPMENT_SLOTS
)
from src.utils.subclass_config import get_available_subclasses, SUBCLASSES

class LootView(discord.ui.View):
    """Vista de comparación para decidir si equipar o vender un drop."""

    def __init__(self, user: discord.Member, loot: dict, current_piece: dict | None):
        super().__init__(timeout=LOOT_TIMEOUT_SECONDS)
        self.user = user
        self.loot = loot
        self.current_piece = current_piece
        self.message = None
        self.resolved = False

    def build_embed(self):
        loot = self.loot
        embed = discord.Embed(
            title=f"{loot['rarity_color']} {loot['name']}",
            description=f"**{loot['rarity']}** · Nivel {loot['item_level']} · {SLOT_EMOJIS.get(loot['slot'], '🔹')} {loot['slot']}",
            color=loot['rarity_hex']
        )
        new_stats_text = format_item_stats_display(loot)
        embed.add_field(name="🆕 Nuevo", value=new_stats_text, inline=True)

        if self.current_piece:
            cp = self.current_piece
            curr_stats_text = format_item_stats_display(cp)
            embed.add_field(name="📦 Actual", value=curr_stats_text, inline=True)
        else:
            embed.add_field(name="📦 Actual", value="— Vacío —", inline=True)

        embed.add_field(name="💰 Precio de venta", value=f"{loot['sell_price']:,} monedas", inline=False)
        embed.set_footer(text=f"Si no respondes en {LOOT_TIMEOUT_SECONDS}s, se vende automáticamente.")
        return embed

    @discord.ui.button(label="🔧 Equipar", style=discord.ButtonStyle.success)
    async def equip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Este drop no es para ti.", ephemeral=True)
            return
        if self.resolved:
            return

        self.resolved = True
        for item in self.children:
            item.disabled = True

        await asyncio.to_thread(
            equip_item, self.user.id, self.loot["slot"], self.loot["name"],
            self.loot["rarity"], self.loot["item_level"], self.loot["primary_stat"],
            self.loot["primary_value"], self.loot["secondaries"], self.loot["passive"],
            self.loot.get("mini_affix", {}).get("key") if self.loot.get("mini_affix") else None,
            self.loot.get("mini_affix", {}).get("value") if self.loot.get("mini_affix") else None,
            self.loot.get("weapon_subtype")
        )

        embed = discord.Embed(
            title="✅ ¡Objeto Equipado!",
            description=f"Te has equipado **{self.loot['name']}** en la ranura de **{self.loot['slot']}**.",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="💰 Vender", style=discord.ButtonStyle.secondary)
    async def sell_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Este drop no es para ti.", ephemeral=True)
            return
        if self.resolved:
            return

        self.resolved = True
        for item in self.children:
            item.disabled = True

        price = self.loot["sell_price"]
        await asyncio.to_thread(add_combat_currency, self.user.id, price)

        embed = discord.Embed(
            title="💰 Objeto Vendido",
            description=f"Has vendido **{self.loot['name']}** por **{format_currency(price)}**.",
            color=discord.Color.gold()
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

class GemShopView(discord.ui.View):
    def __init__(self, user: discord.Member, catalog: list, equipment: dict):
        super().__init__(timeout=120)
        self.user = user
        self.catalog = catalog
        self.equipment = equipment

class ConsumableShopView(discord.ui.View):
    def __init__(self, user: discord.Member, catalog: list):
        super().__init__(timeout=120)
        self.user = user
        self.catalog = catalog

class ClassSelectionView(discord.ui.View):
    def __init__(self, user: discord.Member, current_class: str | None):
        super().__init__(timeout=60)
        self.user = user
        self.selected_class = None
        options = [
            discord.SelectOption(label="Guerrero ⚔️", value="Guerrero"),
            discord.SelectOption(label="Paladín 🛡️", value="Paladín"),
            discord.SelectOption(label="Pícaro 🥷", value="Pícaro"),
            discord.SelectOption(label="Mago 🔥", value="Mago"),
            discord.SelectOption(label="Clérigo ⚕️", value="Clérigo")
        ]
        self.select = discord.ui.Select(placeholder="Elige tu clase", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este selector.", ephemeral=True)
            return
        self.selected_class = self.select.values[0]
        await interaction.response.defer()
        self.stop()

class SubclassSelectionView(discord.ui.View):
    def __init__(self, user: discord.Member, class_name: str, current_subclass: str | None):
        super().__init__(timeout=90)
        self.user = user
        self.selected_subclass = None
        subclasses = get_available_subclasses(class_name)
        options = [
            discord.SelectOption(label=f"{SUBCLASSES[s]['emoji']} {s}", value=s, description=SUBCLASSES[s]['desc'][:100])
            for s in subclasses
        ]
        self.select = discord.ui.Select(placeholder="Elige tu subclase", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ No puedes usar este selector.", ephemeral=True)
            return
        self.selected_subclass = self.select.values[0]
        await interaction.response.defer()
        self.stop()
