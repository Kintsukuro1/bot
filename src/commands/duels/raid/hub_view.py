import discord
import asyncio
from src.utils.raid_config import get_today_boss, BOSS_ABILITIES
from src.utils.combat_progression import get_combat_rank, get_combat_rank_emoji, format_currency
from src.db import get_combat_stats, get_user_equipment, get_guild_poblado, get_user_pets

class RaidHubView(discord.ui.View):
    """Vista del Panel Hub Efímero de Combate y Raids."""

    def __init__(self, user: discord.Member, cog):
        super().__init__(timeout=120)
        self.user = user
        self.cog = cog

    @discord.ui.button(label="⚔️ Crear Raid", style=discord.ButtonStyle.success, row=0)
    async def create_raid_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return

        await interaction.response.send_message("⚔️ **¡Iniciando sala de espera para la Raid!**", ephemeral=True)
        # Lanzar la raid en el canal público
        await self.cog.start_raid_lobby_from_hub(interaction)

    @discord.ui.button(label="🎒 Equipo & Gemas", style=discord.ButtonStyle.primary, row=0)
    async def inventory_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        equip = await asyncio.to_thread(get_user_equipment, self.user.id)
        embed = discord.Embed(
            title=f"🎒 Equipo de Combate — {self.user.display_name}",
            color=discord.Color.dark_teal()
        )
        for slot, piece in equip.items():
            val = piece["item_name"] if piece else "— Vacío —"
            embed.add_field(name=slot, value=val, inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="🐾 Mascotas", style=discord.ButtonStyle.primary, row=0)
    async def pets_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        pets = await asyncio.to_thread(get_user_pets, self.user.id)
        embed = discord.Embed(
            title=f"🐾 Mascotas de {self.user.display_name}",
            color=discord.Color.green()
        )
        if not pets:
            embed.description = "No tienes mascotas registradas. ¡Captura o compra una en `/mascotas`!"
        else:
            lines = [f"{p.get('emoji', '🐾')} **{p.get('name', 'Mascota')}** (Nvl {p.get('level', 1)}) — Lealtad: {p.get('loyalty', 100)}%" for p in pets]
            embed.description = "\n".join(lines)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="🏘️ Poblado", style=discord.ButtonStyle.secondary, row=1)
    async def village_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return

        if not interaction.guild_id:
            await interaction.response.send_message("❌ El poblado solo está disponible en un servidor.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        p_data = await asyncio.to_thread(get_guild_poblado, interaction.guild_id)

        embed = discord.Embed(
            title=f"🏘️ Poblado Comunitario — {interaction.guild.name}",
            description=f"Proyecto Activo: **{p_data.get('proyecto_activo', 'Ninguno')}**\nPuntos Semanales: **{p_data.get('puntos_semanales', 0):,}**",
            color=discord.Color.gold()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="🛒 Tienda PvE", style=discord.ButtonStyle.secondary, row=1)
    async def shop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        from src.db import get_consumable_catalog
        from src.commands.duels.pvp.loot_views import ConsumableShopView
        catalog = await asyncio.to_thread(get_consumable_catalog)

        embed = discord.Embed(
            title="⚔️ Tienda de Raids y Aventura",
            description="Consumibles y brebajes de utilidad para expediciones PvE.",
            color=discord.Color.dark_purple()
        )
        for item in catalog:
            embed.add_field(
                name=f"🧪 {item['name']} — {format_currency(item['price'])}",
                value=f"*{item['description']}*",
                inline=False
            )

        view = ConsumableShopView(interaction.user, catalog)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🏆 Ranking", style=discord.ButtonStyle.secondary, row=1)
    async def ranking_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        from src.db import get_duel_leaderboard
        rows = await asyncio.to_thread(get_duel_leaderboard, "wins", 10)
        embed = discord.Embed(title="🏆 Ranking de Duelos", color=discord.Color.gold())
        if not rows:
            embed.description = "Sin registros."
        else:
            lines = [f"`{i+1}.` User {r[0]} — {r[2]} Victorias (Nv. {r[1]})" for i, r in enumerate(rows)]
            embed.description = "\n".join(lines)
        await interaction.followup.send(embed=embed, ephemeral=True)
