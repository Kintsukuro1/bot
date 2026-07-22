import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
from src.db import (
    get_guild_poblado, get_guild_buildings, set_active_project,
    get_building_level, record_poblado_contribution, get_poblado_leaderboard,
    add_poblado_resources, db_cursor, get_user_pets
)
from src.utils.combat_progression import format_progress_bar

logger = logging.getLogger(__name__)

BUILDINGS_INFO = {
    "Herrería de Combate": {
        "emoji": "🔨",
        "desc": "Reduce costo de remover gemas (-10%/nvl) y transmuta gemas a Nvl 5.",
        "req_base": {"madera": 50, "piedra": 100, "cristal": 20, "solar": 10}
    },
    "Gran Mercado del Servidor": {
        "emoji": "🏬",
        "desc": "Reduce comisiones de mercado/subasta (-1%/nvl) y ofertas comunitarias.",
        "req_base": {"madera": 100, "piedra": 50, "cristal": 30, "solar": 15}
    },
    "Bastión de Raids": {
        "emoji": "🏰",
        "desc": "Otorga escudo de absorción en Raids (+3% HP max/nvl) y reduce CD de Ultimate.",
        "req_base": {"madera": 80, "piedra": 120, "cristal": 40, "solar": 20}
    },
    "Gran Biblioteca Arcana": {
        "emoji": "📚",
        "desc": "Bono de XP de combate global (+3%/nvl) y desbloquea el compendio de bosses.",
        "req_base": {"madera": 120, "piedra": 40, "cristal": 60, "solar": 25}
    },
    "Templo del Alba": {
        "emoji": "⛪",
        "desc": "Desbloquea /oracion diaria (restaura lealtad de mascota y +5% HP) y purificación.",
        "req_base": {"madera": 60, "piedra": 80, "cristal": 50, "solar": 30}
    },
    "Taberna del Aventurero": {
        "emoji": "🍺",
        "desc": "Aumenta chance de cofres y eventos en Aventura (+5%/nvl) y brebajes dobles.",
        "req_base": {"madera": 90, "piedra": 70, "cristal": 25, "solar": 10}
    }
}

def create_poblado_display(guild_name: str, p_data: dict, buildings: dict):
    proyecto_activo = p_data.get("proyecto_activo", "Herrería de Combate")

    embed = discord.Embed(
        title=f"🏘️ Poblado Comunitario — {guild_name}",
        description="¡Unidos para progresar! Todos los miembros aportan jugando Raids y Aventuras.",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/3209/3209995.png")

    recursos_txt = (
        f"🌲 **Madera Ancestral:** {p_data.get('madera', 0):,}\n"
        f"🌋 **Piedra Ígnea:** {p_data.get('piedra', 0):,}\n"
        f"🔮 **Cristal de Sombras:** {p_data.get('cristal', 0):,}\n"
        f"☀️ **Lingote Solar:** {p_data.get('solar', 0):,}"
    )
    embed.add_field(name="📦 Arca de Recursos del Servidor", value=recursos_txt, inline=True)

    puntos_sem = p_data.get("puntos_semanales", 0)
    if puntos_sem >= 2000:
        hitos_txt = f"`[██████████]` {puntos_sem:,}/2,000 pts 🥇 **¡HITO ORO ALCANZADO! (+35% XP / +25% Bronce)**"
    elif puntos_sem >= 800:
        hitos_txt = f"`[{format_progress_bar(puntos_sem, 2000)}]` {puntos_sem:,}/2,000 pts 🥈 **HITO PLATA ALCANZADO (+20% XP)**"
    elif puntos_sem >= 300:
        hitos_txt = f"`[{format_progress_bar(puntos_sem, 800)}]` {puntos_sem:,}/800 pts 🥉 **HITO BRONCE ALCANZADO (+10% XP)**"
    else:
        bar = format_progress_bar(puntos_sem, 300)
        hitos_txt = f"`[{bar}]` {puntos_sem:,}/300 pts (Próximo: 🥉 Hito Bronce)"

    embed.add_field(name="🎯 Hito Semanal de Servidor", value=hitos_txt, inline=False)

    edificios_txt = ""
    for name, info in BUILDINGS_INFO.items():
        lvl = buildings.get(name, 1)
        lvl_tag = f"⭐ Nvl {lvl}/5" if lvl < 5 else "🌟 **NVL MÁXIMO**"
        is_active = " 🛠️ *(En obra)*" if name == proyecto_activo and lvl < 5 else ""
        edificios_txt += f"{info['emoji']} **{name}** ({lvl_tag}){is_active}\n↳ *{info['desc']}*\n"

    embed.add_field(name="🏛️ Edificios del Pueblo", value=edificios_txt, inline=False)
    embed.set_footer(text="Interactúa con los botones de abajo para donar recursos, orar o consultar el ranking.")
    return embed

class DonarRecursosModal(discord.ui.Modal, title="Donar Recursos al Poblado"):
    madera = discord.ui.TextInput(label="🌲 Madera Ancestral", placeholder="Cantidad a donar (Ej: 10)", required=False, default="0")
    piedra = discord.ui.TextInput(label="🌋 Piedra Ígnea", placeholder="Cantidad a donar (Ej: 10)", required=False, default="0")
    cristal = discord.ui.TextInput(label="🔮 Cristal de Sombras", placeholder="Cantidad a donar (Ej: 5)", required=False, default="0")
    solar = discord.ui.TextInput(label="☀️ Lingote Solar", placeholder="Cantidad a donar (Ej: 2)", required=False, default="0")

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            m = max(0, int(self.madera.value or 0))
            p = max(0, int(self.piedra.value or 0))
            c = max(0, int(self.cristal.value or 0))
            s = max(0, int(self.solar.value or 0))
        except ValueError:
            await interaction.response.send_message("❌ Ingresa números enteros válidos.", ephemeral=True)
            return

        total_mats = m + p + c + s
        if total_mats <= 0:
            await interaction.response.send_message("❌ Ingresa al menos 1 material a donar.", ephemeral=True)
            return

        puntos = total_mats * 10
        await asyncio.to_thread(add_poblado_resources, self.guild_id, m, p, c, s, puntos)
        await asyncio.to_thread(record_poblado_contribution, self.guild_id, interaction.user.id, puntos, total_mats)

        embed = discord.Embed(
            title="📦 Donación Registrada",
            description=f"¡Gracias por tu aporte al Poblado! Has donado **{total_mats:,}** materiales (+{puntos:,} pts semanales).",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class PobladoView(discord.ui.View):
    def __init__(self, guild_id: int, user: discord.Member):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.user = user

    @discord.ui.button(label="✨ Oración Diaria", style=discord.ButtonStyle.success, row=0)
    async def pray_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        def _pray():
            lvl = get_building_level(self.guild_id, "Templo del Alba")
            if lvl < 1:
                return False, "El servidor aún no ha construido el **Templo del Alba**."

            pets = get_user_pets(interaction.user.id)
            if not pets:
                return False, "No tienes ninguna mascota para recibir la bendición."

            with db_cursor() as c:
                c.execute("UPDATE UserPets SET Loyalty = 100 WHERE UserID = %s AND Status = 'Activo'", (interaction.user.id,))
                return True, f"✨ ¡Has realizado tu oración diaria en el **Templo del Alba** (Nvl {lvl})! La lealtad de tus mascotas fue restaurada al **100%** y obtienes **+5% HP** para tu próxima expedición."

        success, msg = await asyncio.to_thread(_pray)
        if success:
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {msg}", ephemeral=True)

    @discord.ui.button(label="📦 Donar Recursos", style=discord.ButtonStyle.primary, row=0)
    async def donate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DonarRecursosModal(self.guild_id))

    @discord.ui.button(label="🏆 Top Contribuidores", style=discord.ButtonStyle.secondary, row=0)
    async def top_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        rows = await asyncio.to_thread(get_poblado_leaderboard, self.guild_id, 10)

        embed = discord.Embed(
            title=f"🏆 Mayores Contribuidores — Poblado del Servidor",
            color=discord.Color.gold()
        )

        if not rows:
            embed.description = "Aún no hay contribuciones registradas en este servidor."
        else:
            lines = []
            medals = ["🥇", "🥈", "🥉"]
            for i, r in enumerate(rows):
                user_id, pts, mat = r
                medal = medals[i] if i < 3 else f"`{i+1}.`"
                member = interaction.guild.get_member(user_id)
                name = member.display_name if member else f"Usuario {user_id}"
                lines.append(f"{medal} **{name}** — **{pts:,}** Puntos ({mat:,} donados)")
            embed.description = "\n".join(lines)

        await interaction.followup.send(embed=embed, ephemeral=True)

class Poblado(commands.Cog):
    """Cog para la gestión del Poblado Comunitario por Servidor."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="poblado", description="Muestra el estado del Poblado Comunitario del servidor.")
    async def poblado(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("❌ Este comando solo se puede usar en un servidor de Discord.", ephemeral=True)
            return

        await interaction.response.defer()

        def _fetch_data():
            poblado_data = get_guild_poblado(interaction.guild_id)
            buildings = get_guild_buildings(interaction.guild_id)
            return poblado_data, buildings

        p_data, buildings = await asyncio.to_thread(_fetch_data)

        embed = create_poblado_display(interaction.guild.name, p_data, buildings)
        view = PobladoView(interaction.guild_id, interaction.user)

        await interaction.followup.send(embed=embed, view=view)


    @app_commands.command(name="poblado_construir", description="[ADMIN] Establece qué edificio construir o mejorar a continuación.")
    @app_commands.describe(edificio="Nombre del edificio a priorizar")
    @app_commands.choices(edificio=[
        app_commands.Choice(name="🔨 Herrería de Combate", value="Herrería de Combate"),
        app_commands.Choice(name="🏬 Gran Mercado del Servidor", value="Gran Mercado del Servidor"),
        app_commands.Choice(name="🏰 Bastión de Raids", value="Bastión de Raids"),
        app_commands.Choice(name="📚 Gran Biblioteca Arcana", value="Gran Biblioteca Arcana"),
        app_commands.Choice(name="⛪ Templo del Alba", value="Templo del Alba"),
        app_commands.Choice(name="🍺 Taberna del Aventurero", value="Taberna del Aventurero"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def poblado_construir(self, interaction: discord.Interaction, edificio: app_commands.Choice[str]):
        if not interaction.guild_id:
            await interaction.response.send_message("❌ Este comando solo se puede usar en un servidor.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        success, msg = await asyncio.to_thread(set_active_project, interaction.guild_id, edificio.value)
        if success:
            await interaction.followup.send(f"✅ ¡Proyecto prioritario actualizado! {msg}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {msg}", ephemeral=True)

    @app_commands.command(name="oracion", description="Realiza tu oración diaria en el Templo del Poblado (restaura lealtad de tu mascota).")
    async def oracion(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("❌ Este comando solo se puede usar en un servidor.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        def _pray():
            lvl = get_building_level(interaction.guild_id, "Templo del Alba")
            if lvl < 1:
                return False, "El servidor aún no ha construido el **Templo del Alba**."

            pets = get_user_pets(interaction.user.id)
            if not pets:
                return False, "No tienes ninguna mascota para recibir la bendición."

            # Restaurar lealtad a 100 de las mascotas activas
            with db_cursor() as c:
                c.execute("UPDATE UserPets SET Loyalty = 100 WHERE UserID = %s AND Status = 'Activo'", (interaction.user.id,))
                return True, f"✨ ¡Has realizado tu oración diaria en el **Templo del Alba** (Nvl {lvl})! La lealtad de tus mascotas ha sido restaurada al **100%** y obtienes **+5% HP** para tu próxima aventura."

        success, msg = await asyncio.to_thread(_pray)
        if success:
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {msg}", ephemeral=True)

    @app_commands.command(name="poblado_top", description="Muestra el ranking de mayores aportadores al Poblado del servidor.")
    async def poblado_top(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("❌ Este comando solo se puede usar en un servidor.", ephemeral=True)
            return

        await interaction.response.defer()
        rows = await asyncio.to_thread(get_poblado_leaderboard, interaction.guild_id, 10)

        embed = discord.Embed(
            title=f"🏆 Mayores Contribuidores — Poblado de {interaction.guild.name}",
            color=discord.Color.gold()
        )

        if not rows:
            embed.description = "Aún no hay contribuciones registradas en este servidor."
        else:
            lines = []
            medals = ["🥇", "🥈", "🥉"]
            for i, r in enumerate(rows):
                user_id, pts, mat = r
                medal = medals[i] if i < 3 else f"`{i+1}.`"
                member = interaction.guild.get_member(user_id)
                name = member.display_name if member else f"Usuario {user_id}"
                lines.append(f"{medal} **{name}** — **{pts:,}** Puntos de Contribución ({mat:,} donados)")
            embed.description = "\n".join(lines)

        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Poblado(bot))
    print("Poblado cog loaded successfully.")
