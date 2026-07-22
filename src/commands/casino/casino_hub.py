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

class QuickBetModal(discord.ui.Modal):
    """Modal para ingresar la apuesta y lanzar el juego directamente."""
    def __init__(self, game_key: str, game_name: str, cog):
        super().__init__(title=f"🎲 Apostar en {game_name}")
        self.game_key = game_key
        self.cog = cog

        self.bet_input = discord.ui.TextInput(
            label="Monto de la Apuesta 🪙",
            placeholder="Ejemplo: 500",
            min_length=1,
            max_length=10,
            required=True
        )
        self.add_item(self.bet_input)

    async def on_submit(self, interaction: discord.Interaction):
        val_str = self.bet_input.value.strip()
        if not val_str.isdigit() or int(val_str) <= 0:
            await interaction.response.send_message("❌ Ingresa un monto entero válido mayor a 0.", ephemeral=True)
            return

        apuesta = int(val_str)
        user_id = interaction.user.id
        user_name = interaction.user.name

        if self.game_key == "mines":
            from src.commands.casino.mines import MinesSetupView, calculate_multiplier
            await interaction.response.defer()
            view = MinesSetupView(user_id, apuesta, user_name)
            embed = discord.Embed(
                title="💣 Configuración de Buscaminas",
                description=(
                    f"💰 Apuesta: **{apuesta}**\n"
                    f"💣 Bombas seleccionadas: **3**\n\n"
                    f"Multiplicador al primer acierto: **x{calculate_multiplier(3, 20, 1):.2f}**\n"
                    "A mayor cantidad de bombas, mayor el riesgo y las ganancias."
                ),
                color=discord.Color.blue()
            )
            msg = await interaction.followup.send(embed=embed, view=view)
            view.message = msg

        elif self.game_key == "slots":
            slots_cog = self.cog.bot.get_cog("Slots")
            if slots_cog:
                await slots_cog.slots(interaction, apuesta)
            else:
                await interaction.response.send_message("❌ Módulo de tragamonedas no disponible.", ephemeral=True)

        elif self.game_key == "blackjack":
            bj_cog = self.cog.bot.get_cog("Blackjack")
            if bj_cog:
                await bj_cog.blackjack(interaction, apuesta)
            else:
                await interaction.response.send_message("❌ Módulo de blackjack no disponible.", ephemeral=True)

        elif self.game_key == "crash":
            crash_cog = self.cog.bot.get_cog("Crash")
            if crash_cog:
                await crash_cog.crash(interaction, apuesta)
            else:
                await interaction.response.send_message("❌ Módulo de crash no disponible.", ephemeral=True)

        elif self.game_key == "plinko":
            plinko_cog = self.cog.bot.get_cog("Plinko")
            if plinko_cog:
                await plinko_cog.plinko(interaction, apuesta)
            else:
                await interaction.response.send_message("❌ Módulo de plinko no disponible.", ephemeral=True)

        elif self.game_key == "coinflip":
            coin_cog = self.cog.bot.get_cog("Coinflip")
            if coin_cog:
                await coin_cog.coinflip_cmd(interaction, apuesta)
            else:
                await interaction.response.send_message("❌ Módulo de coinflip no disponible.", ephemeral=True)

        elif self.game_key == "roulette":
            roulette_cog = self.cog.bot.get_cog("Roulette")
            if roulette_cog:
                await roulette_cog.roulette(interaction, apuesta)
            else:
                await interaction.response.send_message("❌ Módulo de ruleta no disponible.", ephemeral=True)


class RobarModal(discord.ui.Modal):
    """Modal para realizar un robo especificando ID de usuario o mención."""
    def __init__(self, cog):
        super().__init__(title="🥷 Ejecutar Robo")
        self.cog = cog
        self.target_input = discord.ui.TextInput(
            label="ID o Nombre del Usuario Objetivo",
            placeholder="Ingresa la ID del usuario a robar...",
            min_length=3,
            max_length=30,
            required=True
        )
        self.add_item(self.target_input)

    async def on_submit(self, interaction: discord.Interaction):
        target_str = self.target_input.value.strip().replace("<@", "").replace(">", "").replace("!", "")
        if not target_str.isdigit():
            await interaction.response.send_message("❌ Ingresa una ID de usuario numérica válida.", ephemeral=True)
            return

        target_id = int(target_str)
        target_user = interaction.guild.get_member(target_id) if interaction.guild else None
        if not target_user:
            await interaction.response.send_message("❌ No se encontró a ese usuario en el servidor.", ephemeral=True)
            return

        robar_cog = self.cog.bot.get_cog("Robar")
        if robar_cog:
            await robar_cog.robar(interaction, target_user)
        else:
            await interaction.response.send_message("❌ Módulo de robos no disponible.", ephemeral=True)


class BankTransactionModal(discord.ui.Modal):
    """Modal para realizar depósitos o retiros bancarios."""
    def __init__(self, is_deposit: bool, cog):
        super().__init__(title="📥 Depositar al Banco" if is_deposit else "📤 Retirar del Banco")
        self.is_deposit = is_deposit
        self.cog = cog
        self.amount_input = discord.ui.TextInput(
            label="Monto de Monedas",
            placeholder="Ejemplo: 1000",
            min_length=1,
            max_length=12,
            required=True
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        val_str = self.amount_input.value.strip()
        if not val_str.isdigit() or int(val_str) <= 0:
            await interaction.response.send_message("❌ Ingresa un monto entero válido.", ephemeral=True)
            return

        monto = int(val_str)
        banco_cog = self.cog.bot.get_cog("Banco")
        if banco_cog:
            if self.is_deposit:
                await banco_cog.depositar(interaction, monto)
            else:
                await banco_cog.retirar(interaction, monto)
        else:
            await interaction.response.send_message("❌ Módulo de banco no disponible.", ephemeral=True)


class BankActionsView(discord.ui.View):
    """Vista de acciones de banco con botones Depositar y Retirar."""
    def __init__(self, user: discord.Member, cog):
        super().__init__(timeout=60)
        self.user = user
        self.cog = cog

    @discord.ui.button(label="📥 Depositar", style=discord.ButtonStyle.success)
    async def deposit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return
        await interaction.response.send_modal(BankTransactionModal(is_deposit=True, cog=self.cog))

    @discord.ui.button(label="📤 Retirar", style=discord.ButtonStyle.danger)
    async def withdraw_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return
        await interaction.response.send_modal(BankTransactionModal(is_deposit=False, cog=self.cog))


class CasinoGamesSelectView(discord.ui.View):
    """Vista efímera de selección y lanzamiento directo de juegos de casino."""
    def __init__(self, user: discord.Member, cog):
        super().__init__(timeout=60)
        self.user = user
        self.cog = cog

        options = [
            discord.SelectOption(label="🎰 Tragamonedas", value="slots", description="Lanzar tragamonedas"),
            discord.SelectOption(label="🃏 Blackjack", value="blackjack", description="Lanzar partidas de 21"),
            discord.SelectOption(label="🎲 Ruleta", value="roulette", description="Lanzar ruleta europea"),
            discord.SelectOption(label="📈 Crash / Cohete", value="crash", description="Lanzar cohete multiplicador"),
            discord.SelectOption(label="💣 Minas", value="mines", description="Lanzar campo minado"),
            discord.SelectOption(label="🟢 Plinko", value="plinko", description="Lanzar bola de plinko"),
            discord.SelectOption(label="🪙 Coinflip", value="coinflip", description="Lanzar moneda de la suerte"),
        ]
        self.select = discord.ui.Select(placeholder="🎮 Selecciona un juego para apostar...", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta opción no es para ti.", ephemeral=True)
            return

        val = self.select.values[0]
        names = {
            "slots": "Tragamonedas",
            "blackjack": "Blackjack",
            "roulette": "Ruleta",
            "crash": "Crash / Cohete",
            "mines": "Buscaminas",
            "plinko": "Plinko",
            "coinflip": "Coinflip"
        }
        name = names.get(val, "Juego")
        modal = QuickBetModal(val, name, self.cog)
        await interaction.response.send_modal(modal)


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

        view = CasinoGamesSelectView(self.user, self.cog)
        embed = discord.Embed(
            title="🎮 Menú de Juegos de Casino",
            description="Selecciona cualquier modalidad en el menú desplegable para ingresar tu apuesta y jugar de inmediato:",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🥷 Robar", style=discord.ButtonStyle.danger, row=0)
    async def rob_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return

        await interaction.response.send_modal(RobarModal(self.cog))

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
                f"Usa los botones para depositar o retirar fondos:"
            ),
            color=discord.Color.blue()
        )
        view = BankActionsView(self.user, self.cog)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="📈 Inversiones", style=discord.ButtonStyle.secondary, row=1)
    async def investments_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return

        bolsa_cog = self.cog.bot.get_cog("BolsaCog")
        if bolsa_cog:
            await bolsa_cog.bolsa(interaction)
        else:
            await interaction.response.send_message("❌ Módulo de bolsa no disponible.", ephemeral=True)


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
