import discord
from discord.ext import commands
from discord import app_commands
from src.commands.shop.black_market_items import BLACK_MARKET
from src.db import get_balance, set_balance, deduct_balance, registrar_transaccion, ensure_user
import asyncio

class DopeCaballoSelect(discord.ui.Select):
    def __init__(self, race_view):
        self.race_view = race_view
        options = [
            discord.SelectOption(label=h['name'], emoji=h['emoji'], value=str(i))
            for i, h in enumerate(race_view.horses)
        ]
        super().__init__(placeholder="Elige un caballo para inyectar...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.race_view.started:
            await interaction.response.send_message("❌ La carrera ya ha comenzado.", ephemeral=True)
            return

        horse_idx = int(self.values[0])
        user_id = interaction.user.id
        
        # Verificar y descontar dinero
        costo_doping = 5000
        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)
        
        success, balance = await asyncio.to_thread(deduct_balance, user_id, costo_doping)
        if not success:
            await interaction.response.send_message(f"❌ No tienes suficientes monedas. Necesitas {costo_doping} 🪙.", ephemeral=True)
            return
        
        horse_name = self.race_view.horses[horse_idx]['name']
        horse_emoji = self.race_view.horses[horse_idx]['emoji']

        await asyncio.to_thread(registrar_transaccion, user_id, -costo_doping, f"Mercado Negro: Doping para {horse_name}")
        
        # Incrementar doping en la vista de la carrera
        self.race_view.horse_doping[horse_idx] += 1
        dosis_actual = self.race_view.horse_doping[horse_idx]
        
        if dosis_actual > 3:
            msg = f"💉 Has inyectado una dosis letal a {horse_emoji} **{horse_name}**... El caballo no resistirá la carrera (Sobredosis 💀)."
        else:
            msg = f"💉 Has inyectado doping a {horse_emoji} **{horse_name}**. Correrá mucho más rápido. (Dosis acumuladas: {dosis_actual}/3)"
            
        await interaction.response.send_message(msg, ephemeral=True)

class DopeCaballoView(discord.ui.View):
    def __init__(self, race_view):
        super().__init__(timeout=60)
        self.add_item(DopeCaballoSelect(race_view))

class BlackMarket(commands.Cog):
    """Cog para mostrar mejoras permanentes del mercado negro."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="blackmarket", description="Muestra las mejoras permanentes del mercado negro.")
    async def blackmarket(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        from src.db import get_user_prestige_level
        prestige_level = await asyncio.to_thread(get_user_prestige_level, user_id)

        embed = discord.Embed(
            title="🕶️ Black Market (Mejoras Permanentes)",
            description="Mejoras exclusivas para los más arriesgados.",
            color=discord.Color.dark_purple()
        )
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/3062/3062634.png")

        # Filtrar ítems visibles (prestige_required <= prestige_level)
        visible_items = [item for item in BLACK_MARKET if item.get("prestige_required", 0) <= prestige_level]

        # Separar en normales y exclusivos
        normal_items = [item for item in visible_items if item.get("prestige_required", 0) < 2]
        prestige_items = [item for item in visible_items if item.get("prestige_required", 0) >= 2]

        for item in normal_items:
            embed.add_field(
                name=f"{item['nombre']} — {item['precio']} 🪙",
                value=f"`ID:` `{item['id']}`\n{item['descripcion']}",
                inline=False
            )

        if prestige_items:
            embed.add_field(
                name="───────────────────",
                value="🌟 **EXCLUSIVO PRESTIGIO II** 🌟",
                inline=False
            )
            for item in prestige_items:
                embed.add_field(
                    name=f"{item['nombre']} — {item['precio']} 🪙",
                    value=f"`ID:` `{item['id']}`\n{item['descripcion']}",
                    inline=False
                )

        embed.set_footer(text="Usa /comprar_mejora <ID> para adquirir una mejora permanente.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="dopear_caballo", description="[MERCADO NEGRO] Inyecta sustancias a un caballo para su próxima carrera (Costo: 5000).")
    async def dopear_caballo(self, interaction: discord.Interaction):
        horse_race_cog = interaction.client.get_cog("HorseRace")
        if not horse_race_cog or interaction.channel_id not in horse_race_cog.active_races:
            await interaction.response.send_message("❌ No hay ninguna carrera activa o en preparación en este canal. ¡Primero inicia una carrera con `/horse_race`!", ephemeral=True)
            return

        race_view = horse_race_cog.active_races[interaction.channel_id]
        if race_view.started:
            await interaction.response.send_message("❌ La carrera ya ha comenzado, no puedes dopear caballos ahora.", ephemeral=True)
            return

        embed = discord.Embed(
            title="💉 Mercado Negro: Doping de Caballos",
            description="Selecciona un caballo para inyectarle una dosis especial. Correrá mucho más rápido en esta carrera.\n\n⚠️ **Cuidado:** Si un caballo recibe **más de 3 dosis**, sufrirá un infarto al iniciar la carrera y perderá automáticamente.\n\n💰 **Costo por dosis:** 5000 monedas.",
            color=discord.Color.dark_red()
        )
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/3062/3062634.png")
        view = DopeCaballoView(race_view)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(BlackMarket(bot))
    print("BlackMarket cog loaded successfully.")
