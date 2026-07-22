import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
from src.db import get_balance, db_cursor, get_user_pets
from src.utils.combat_progression import format_currency


logger = logging.getLogger(__name__)

def get_gambler_info(user_id: int) -> dict:
    """Obtiene información del nivel de Gambler del usuario."""
    with db_cursor() as c:
        c.execute("""
            SELECT GamblerLevel, GamblerXP, TotalValidBets, TotalBetVolume
            FROM GamblerProgress WHERE UserID = %s
        """, (user_id,))
        row = c.fetchone()
        if not row:
            return {"level": 1, "xp": 0, "bets": 0, "volume": 0}
        return {"level": row[0], "xp": row[1], "bets": row[2], "volume": row[3]}

def get_bank_info(user_id: int) -> dict:
    """Obtiene el saldo depositado en el banco del usuario."""
    with db_cursor() as c:
        c.execute("SELECT BankBalance FROM Users WHERE UserID = %s", (user_id,))
        row = c.fetchone()
        return {"bank_balance": row[0] if row and row[0] is not None else 0}

class CasinoGamesSelectView(discord.ui.View):
    """Vista efímera de selección de juegos de casino."""
    def __init__(self, user: discord.Member):
        super().__init__(timeout=60)
        self.user = user

        options = [
            discord.SelectOption(label="🎰 Tragamonedas", value="slots", description="/apuesta_tragamonedas <apuesta>"),
            discord.SelectOption(label="🃏 Blackjack", value="blackjack", description="/apuesta_blackjack <apuesta>"),
            discord.SelectOption(label="🎲 Ruleta", value="roulette", description="/apuesta_ruleta <apuesta> <opcion>"),
            discord.SelectOption(label="📈 Crash / Cohete", value="crash", description="/apuesta_cohete <apuesta>"),
            discord.SelectOption(label="💣 Minas", value="mines", description="/apuesta_minas <apuesta> <minas>"),
            discord.SelectOption(label="🟢 Plinko", value="plinko", description="/apuesta_plinko <apuesta>"),
            discord.SelectOption(label="🪙 Coinflip", value="coinflip", description="/apuesta_moneda <apuesta> <cara/cruz>"),
            discord.SelectOption(label="🎟️ Lotería", value="loto", description="/loto comprar"),
        ]
        self.select = discord.ui.Select(placeholder="🎮 Selecciona un juego para ver su comando...", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta opción no es para ti.", ephemeral=True)
            return

        val = self.select.values[0]
        commands_info = {
            "slots": ("🎰 Tragamonedas", "Usa `/apuesta_tragamonedas <cantidad>` para girar los rodillos."),
            "blackjack": ("🃏 Blackjack", "Usa `/apuesta_blackjack <cantidad>` para jugar 21 contra la banca."),
            "roulette": ("🎲 Ruleta", "Usa `/apuesta_ruleta <cantidad> <rojo/negro/verde/numero>` para apostar."),
            "crash": ("📈 Crash / Cohete", "Usa `/apuesta_cohete <cantidad>` para arriesgar y retirar a tiempo."),
            "mines": ("💣 Minas", "Usa `/apuesta_minas <cantidad> <minas>` para encontrar diamantes."),
            "plinko": ("🟢 Plinko", "Usa `/apuesta_plinko <cantidad>` para soltar la bola."),
            "coinflip": ("🪙 Coinflip", "Usa `/apuesta_moneda <cantidad> <cara/cruz>` para duplicar tu apuesta."),
            "loto": ("🎟️ Lotería", "Usa `/loto comprar` para adquirir tu boleto del sorteo acumulado.")
        }
        title, desc = commands_info.get(val, ("Juego de Casino", "Usa los comandos del casino."))
        embed = discord.Embed(title=title, description=desc, color=discord.Color.gold())
        await interaction.response.edit_message(embed=embed, view=self)


class CasinoHubView(discord.ui.View):
    """Vista del Panel Hub Efímero del Casino y Economía."""

    def __init__(self, user: discord.Member, cog):
        super().__init__(timeout=120)
        self.user = user
        self.cog = cog

    @discord.ui.button(label="🎮 Juegos", style=discord.ButtonStyle.success, row=0)
    async def games_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return

        view = CasinoGamesSelectView(self.user)
        embed = discord.Embed(
            title="🎮 Menú Completo de Juegos de Casino",
            description="Selecciona cualquier modalidad de juego para desplegar sus instrucciones y comando:",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🥷 Robar", style=discord.ButtonStyle.danger, row=0)
    async def rob_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🥷 Sistema de Robo",
            description="Usa el comando `/robar usuario:@usuario` para intentar hurtar un porcentaje del saldo en mano de otra persona.\n\n⚠️ *¡Atención! Si el robo falla, serás multado por las autoridades.*",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🏦 Banco", style=discord.ButtonStyle.primary, row=0)
    async def bank_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        b_info = await asyncio.to_thread(get_bank_info, self.user.id)
        u_bal = await asyncio.to_thread(get_balance, self.user.id)

        embed = discord.Embed(
            title=f"🏦 Banco Central — {self.user.display_name}",
            description=(
                f"💵 **Saldo en Mano:** **{format_currency(u_bal)}**\n"
                f"🏦 **Saldo en Banco:** **{format_currency(b_info['bank_balance'])}**\n\n"
                f"Usa `/depositar <cantidad>` para proteger tus fondos o `/retirar <cantidad>` para disponer de tu dinero."
            ),
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="📈 Inversiones", style=discord.ButtonStyle.secondary, row=1)
    async def investments_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📈 Mercado de Valores e Inversiones",
            description="Usa el comando `/bolsa` para consultar las acciones, criptos e índices en tiempo real y comprar o vender títulos financieros.",
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🐾 Mascota", style=discord.ButtonStyle.secondary, row=1)
    async def pet_button(self, interaction: discord.Interaction, button: discord.ui.Button):
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
            embed.description = "No tienes mascotas registradas. ¡Revisa la tienda o usa `/mascotas`!"
        else:
            lines = [f"{p.get('emoji', '🐾')} **{p.get('name', 'Mascota')}** (Nvl {p.get('level', 1)}) — Lealtad: {p.get('loyalty', 100)}%" for p in pets]
            embed.description = "\n".join(lines)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="👤 Perfil", style=discord.ButtonStyle.secondary, row=1)
    async def profile_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        info = await asyncio.to_thread(get_gambler_info, self.user.id)
        balance = await asyncio.to_thread(get_balance, self.user.id)
        b_info = await asyncio.to_thread(get_bank_info, self.user.id)

        embed = discord.Embed(
            title=f"👤 Perfil Económico & Gambler — {self.user.display_name}",
            color=discord.Color.gold()
        )
        embed.add_field(name="💰 Saldo en Mano", value=f"**{format_currency(balance)}**", inline=True)
        embed.add_field(name="🏦 Saldo en Banco", value=f"**{format_currency(b_info['bank_balance'])}**", inline=True)
        embed.add_field(name="🌟 Nivel Gambler", value=f"**Nivel {info['level']}** ({info['xp']:,} XP)", inline=False)
        embed.add_field(name="🎰 Apuestas Jugadas", value=f"**{info['bets']:,}** partidas", inline=True)
        embed.add_field(name="📈 Volumen Apostado", value=f"**{format_currency(info['volume'])}**", inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)


class CasinoHub(commands.Cog):
    """Cog principal para el Panel Hub Efímero del Casino y Economía."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="casino", description="Abre el Salón Principal de Casino y Economía (Panel Efímero Privado)")
    async def casino_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

        balance = await asyncio.to_thread(get_balance, user_id)
        info = await asyncio.to_thread(get_gambler_info, user_id)

        embed = discord.Embed(
            title="🎰 Casino Lounge & Centro Económico",
            description=(
                f"Bienvenido al Centro Económico, **{interaction.user.display_name}**.\n\n"
                f"💰 **Saldo en Mano:** **{format_currency(balance)}**\n"
                f"🌟 **Rango Gambler:** Nivel **{info['level']}** ({info['xp']:,} XP)\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Usa los botones interactivos para explorar el casino y la economía:"
            ),
            color=discord.Color.dark_gold()
        )
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/1055/1055823.png")
        embed.set_footer(text="Panel Efímero Privado · Únicamente tú ves este menú")

        view = CasinoHubView(interaction.user, self)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(CasinoHub(bot))
    logger.info("CasinoHub cog loaded successfully.")
