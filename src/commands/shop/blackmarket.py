import discord
from discord.ext import commands
from discord import app_commands
from src.commands.shop.black_market_items import BLACK_MARKET
from src.db import get_balance, set_balance, deduct_balance, registrar_transaccion, ensure_user, comprar_item_tienda
from src.services.shop_rotation_service import get_rotation_info, select_rotated_items, BLACKMARKET_ROTATION_SECONDS, get_stock_remaining, consume_stock
import asyncio

def get_current_blackmarket_items():
    """Devuelve los 7 ítems activos en el Blackmarket para la rotación actual de 3h."""
    return select_rotated_items(BLACK_MARKET, count=7, rotation_seconds=BLACKMARKET_ROTATION_SECONDS)

class DopeCaballoSelect(discord.ui.Select):
    def __init__(self, race_view):
        self.race_view = race_view
        options = [
            discord.SelectOption(label=h['name'], emoji=h['emoji'], value=str(i))
            for i, h in enumerate(race_view.horses)
        ]
        super().__init__(placeholder="Elige tu caballo apostado para inyectar...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.race_view.started:
            await interaction.response.send_message("❌ La carrera ya ha comenzado.", ephemeral=True)
            return

        user_id = interaction.user.id
        horse_idx = int(self.values[0])

        # Punto 1A (Anti-Griefing): Solo puedes dopear al caballo al que le has apostado
        if user_id not in self.race_view.bets or self.race_view.bets[user_id]['horse_idx'] != horse_idx:
            await interaction.response.send_message(
                "❌ **Acceso Denegado:** Solo puedes administrar sustancias al caballo en el que has apostado tu dinero.",
                ephemeral=True
            )
            return

        dosis_actual = self.race_view.horse_doping.get(horse_idx, 0)
        if dosis_actual >= 3:
            await interaction.response.send_message("❌ Este caballo ya ha alcanzado el límite máximo de 3 dosis de dopaje.", ephemeral=True)
            return

        # Punto 3 (Costo Escalonado): 1a: 5k, 2a: 15k, 3a: 35k
        costos = [5000, 15000, 35000]
        costo_doping = costos[dosis_actual]

        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)
        success, balance = await asyncio.to_thread(deduct_balance, user_id, costo_doping)
        if not success:
            await interaction.response.send_message(f"❌ No tienes suficiente dinero. La dosis {dosis_actual + 1} cuesta **{costo_doping:,} 🪙**.", ephemeral=True)
            return

        horse_name = self.race_view.horses[horse_idx]['name']
        horse_emoji = self.race_view.horses[horse_idx]['emoji']

        await asyncio.to_thread(registrar_transaccion, user_id, -costo_doping, f"Mercado Negro: Doping dosis {dosis_actual + 1} para {horse_name}")

        self.race_view.horse_doping[horse_idx] += 1
        dosis_nueva = self.race_view.horse_doping[horse_idx]

        # Punto 3 (Ajuste de Cuota): reducir cuota de pago al recibir dopaje
        old_mult = self.race_view.multipliers[horse_idx]
        new_mult = max(1.1, round(old_mult * 0.75, 1))
        self.race_view.multipliers[horse_idx] = new_mult

        # Registrar doper para posibles multas post-carrera
        if not hasattr(self.race_view, "dopers"):
            self.race_view.dopers = {}
        self.race_view.dopers[user_id] = (horse_idx, dosis_nueva)

        msg = (
            f"💉 Has inyectado la **dosis {dosis_nueva}/3** a {horse_emoji} **{horse_name}** por **{costo_doping:,} 🪙**.\n"
            f"📉 La cuota del caballo se redujo de `x{old_mult}` a `x{new_mult}` por aviso médico.\n"
            f"🤫 *Información confidencial: La cantidad de dosis se mantendrá en secreto hasta el inicio de la carrera.*"
        )
        await interaction.response.send_message(msg, ephemeral=True)
        await self.race_view.update_embed()

class DopeCaballoView(discord.ui.View):
    def __init__(self, race_view):
        super().__init__(timeout=60)
        self.add_item(DopeCaballoSelect(race_view))


class BlackMarket(commands.Cog):
    """Cog para mostrar mejoras y artefactos del Mercado Negro en rotación de 3h."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="blackmarket", description="Muestra las mejoras exclusivas del Mercado Negro (Stock rotativo 3h).")
    async def blackmarket(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        from src.db import get_user_prestige_level
        prestige_level = await asyncio.to_thread(get_user_prestige_level, user_id)

        active_items = get_current_blackmarket_items()
        _, _, time_str = get_rotation_info(BLACKMARKET_ROTATION_SECONDS)

        embed = discord.Embed(
            title="🕶️ Black Market — Artefactos & Mejoras de Oficio",
            description=f" Stock exclusivo que rota cada **3 horas**.\n⏱️ **Próxima rotación en:** `{time_str}`",
            color=discord.Color.dark_purple()
        )
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/3062/3062634.png")

        for item in active_items:
            req = item.get("prestige_required", 0)
            if prestige_level >= req:
                job_tag = f" `[{item['job'].upper()}]`" if "job" in item else ""
                stock_rem = await asyncio.to_thread(get_stock_remaining, "blackmarket", item, BLACKMARKET_ROTATION_SECONDS)
                stock_tag = f" (Stock: **{stock_rem}**)" if stock_rem > 0 else " **(❌ AGOTADO)**"
                embed.add_field(
                    name=f"{item['nombre']} — {item['precio']:,} 🪙{job_tag}{stock_tag}",
                    value=f"`ID:` `{item['id']}`\n{item['descripcion']}",
                    inline=False
                )

        embed.set_footer(text="Usa /comprar_mejora <ID> para adquirir un artefacto o mejora del Mercado Negro.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="comprar_mejora", description="Compra una mejora o artefacto del Mercado Negro por su ID.")
    @app_commands.describe(mejora_id="ID de la mejora a comprar")
    async def comprar_mejora(self, interaction: discord.Interaction, mejora_id: int):
        user_id = interaction.user.id
        user_name = interaction.user.name

        active_items = get_current_blackmarket_items()
        item = next((i for i in active_items if i["id"] == mejora_id), None)

        if not item:
            await interaction.response.send_message("❌ Este artefacto no está en el stock rotativo actual del Mercado Negro.", ephemeral=True)
            return

        from src.db import get_user_prestige_level
        prestige_level = await asyncio.to_thread(get_user_prestige_level, user_id)
        if item.get("prestige_required", 0) > prestige_level:
            await interaction.response.send_message("❌ Requieres un nivel de Prestigio más alto para esta mejora.", ephemeral=True)
            return

        # Consumir 1 unidad del stock rotativo del Blackmarket
        has_stock = await asyncio.to_thread(consume_stock, "blackmarket", item, BLACKMARKET_ROTATION_SECONDS)
        if not has_stock:
            await interaction.response.send_message("❌ Este artefacto se ha **agotado** en la rotación actual del Mercado Negro.", ephemeral=True)
            return

        precio = item["precio"]
        success, balance = await asyncio.to_thread(deduct_balance, user_id, precio)
        if not success:
            await interaction.response.send_message(f"❌ No tienes suficiente saldo ({precio:,} 🪙) para comprar este artefacto.", ephemeral=True)
            return

        # Guardar en inventario de usuario con ID desplazado 1000 para indicar BM
        db_item_id = item["id"] + 1000
        from datetime import datetime, timedelta
        expiry = datetime.now() + timedelta(days=3650)
        await asyncio.to_thread(comprar_item_tienda, user_id, db_item_id, 0, expiry)
        await asyncio.to_thread(registrar_transaccion, user_id, -precio, f"Mercado Negro: {item['nombre']}")

        embed = discord.Embed(
            title="🕶️ Compra en Mercado Negro Exitosa",
            description=f"¡Has adquirido **{item['nombre']}**!",
            color=discord.Color.purple()
        )
        embed.add_field(name="💰 Precio Pagado", value=f"{precio:,} monedas", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="dopear_caballo", description="[MERCADO NEGRO] Inyecta sustancias a un caballo para su próxima carrera (Costo: 5000).")
    async def dopear_caballo(self, interaction: discord.Interaction):
        horse_race_cog = interaction.client.get_cog("HorseRace")
        if not horse_race_cog or interaction.channel_id not in horse_race_cog.active_races:
            await interaction.response.send_message("❌ No hay ninguna carrera activa en este canal. ¡Primero inicia una con `/horse_race`!", ephemeral=True)
            return

        race_view = horse_race_cog.active_races[interaction.channel_id]
        if race_view.started:
            await interaction.response.send_message("❌ La carrera ya comenzó.", ephemeral=True)
            return

        embed = discord.Embed(
            title="💉 Mercado Negro: Doping de Caballos",
            description="Selecciona un caballo para inyectarle una dosis especial.\n\n⚠️ **Cuidado:** Si recibe **más de 3 dosis**, sufrirá un infarto (Sobredosis 💀).\n\n💰 **Costo:** 5,000 monedas.",
            color=discord.Color.dark_red()
        )
        view = DopeCaballoView(race_view)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(BlackMarket(bot))
    print("BlackMarket cog loaded successfully.")
