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

        elif self.game_key == "casino_war":
            cw_cog = self.cog.bot.get_cog("CasinoWarCog")
            if cw_cog:
                await cw_cog.casino_war_cmd(interaction, apuesta)
            else:
                await interaction.response.send_message("❌ Módulo de Casino War no disponible.", ephemeral=True)

        elif self.game_key == "higher_lower":
            hl_cog = self.cog.bot.get_cog("HigherLower")
            if hl_cog:
                await hl_cog.higher_lower(interaction, apuesta)
            else:
                await interaction.response.send_message("❌ Módulo de Higher or Lower no disponible.", ephemeral=True)

        elif self.game_key == "liars_dice":
            ld_cog = self.cog.bot.get_cog("LiarsDiceCog")
            if ld_cog:
                await ld_cog.liars_dice_cmd(interaction, apuesta)
            else:
                await interaction.response.send_message("❌ Módulo de Dados de Mentiroso no disponible.", ephemeral=True)

        elif self.game_key == "russian_roulette":
            rr_cog = self.cog.bot.get_cog("RussianRoulette")
            if rr_cog:
                await rr_cog.russian_roulette(interaction, apuesta)
            else:
                await interaction.response.send_message("❌ Módulo de Ruleta Rusa no disponible.", ephemeral=True)

class RPSBetModal(discord.ui.Modal, title="⚔️ Duelo Piedra, Papel o Tijera"):
    apuesta_input = discord.ui.TextInput(
        label="Monto de la Apuesta 🪙",
        placeholder="Ej: 1000",
        required=True
    )

    def __init__(self, oponente: discord.Member, cog):
        super().__init__()
        self.oponente = oponente
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            apuesta = int(self.apuesta_input.value.strip())
            if apuesta <= 0:
                await interaction.response.send_message("❌ La apuesta debe ser mayor a 0.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Monto de apuesta inválido.", ephemeral=True)
            return

        rps_cog = self.cog.bot.get_cog("RPSBet")
        if rps_cog:
            await rps_cog.rps_bet(interaction, self.oponente, apuesta)
        else:
            await interaction.response.send_message("❌ Módulo de Piedra, Papel o Tijeras no disponible.", ephemeral=True)

class RPSUserSelectView(discord.ui.View):
    """Vista con desplegable nativo de miembros para seleccionar oponente de RPS."""
    def __init__(self, user: discord.Member, cog):
        super().__init__(timeout=60)
        self.user = user
        self.cog = cog

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="⚔️ Selecciona al oponente a retar de la lista...")
    async def select_oponent(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta opción no es para ti.", ephemeral=True)
            return

        oponente = select.values[0]
        if not isinstance(oponente, discord.Member) and interaction.guild:
            oponente = interaction.guild.get_member(oponente.id) or oponente

        modal = RPSBetModal(oponente, self.cog)
        await interaction.response.send_modal(modal)

class RobarUserSelectView(discord.ui.View):
    """Vista con menú desplegable nativo de miembros para seleccionar la víctima."""
    def __init__(self, user: discord.Member, cog):
        super().__init__(timeout=60)
        self.user = user
        self.cog = cog

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="🥷 Selecciona a la víctima de la lista...")
    async def select_victim(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta opción no es para ti.", ephemeral=True)
            return

        victim = select.values[0]
        if not isinstance(victim, discord.Member) and interaction.guild:
            victim = interaction.guild.get_member(victim.id) or victim

        robar_cog = self.cog.bot.get_cog("Robar")
        if robar_cog:
            await robar_cog._robar_logica(interaction, victim, is_slash=True)
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
        banco_cog = self.cog.bot.get_cog("BancoCog") or self.cog.bot.get_cog("Banco")
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
            discord.SelectOption(label="🎰 Tragamonedas", value="slots", description="Tragamonedas clásico de 3 carretes"),
            discord.SelectOption(label="🃏 Blackjack", value="blackjack", description="Partidas de 21 contra la banca"),
            discord.SelectOption(label="🎲 Ruleta Europea", value="roulette", description="Ruleta de apuestas de números y colores"),
            discord.SelectOption(label="📈 Crash / Cohete", value="crash", description="Cohete multiplicador con retiro a tiempo"),
            discord.SelectOption(label="💣 Buscaminas", value="mines", description="Campo minado con multiplicador progresivo"),
            discord.SelectOption(label="🟢 Plinko", value="plinko", description="Pelota rebotante con multiplicadores"),
            discord.SelectOption(label="🪙 Coinflip", value="coinflip", description="Lanzamiento de moneda cara o cruz"),
            discord.SelectOption(label="⚔️ Casino War", value="casino_war", description="Guerra de cartas de mayor valor"),
            discord.SelectOption(label="🎴 Higher or Lower", value="higher_lower", description="Adivina si la siguiente carta es mayor o menor"),
            discord.SelectOption(label="🏇 Carrera de Caballos", value="horse_race", description="Pista de carreras de 60s con apuestas"),
            discord.SelectOption(label="🎲 Dados de Mentiroso", value="liars_dice", description="Mesa multijugador de faroleo con dados"),
            discord.SelectOption(label="🔫 Ruleta Rusa", value="russian_roulette", description="Juego de tensión multijugador con cargador"),
            discord.SelectOption(label="✂️ Piedra, Papel o Tijeras", value="rps_bet", description="Duelo PvP directo por dinero"),
            discord.SelectOption(label="🎟️ Lotería / Loto", value="loto", description="Pozo acumulado diario y boletos"),
            discord.SelectOption(label="🛡️ Provably Fair", value="provably_fair", description="Verificador criptográfico de transparencia"),
        ]
        self.select = discord.ui.Select(placeholder="🎮 Selecciona un juego para apostar...", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta opción no es para ti.", ephemeral=True)
            return

        val = self.select.values[0]

        if val == "horse_race":
            hr_cog = self.cog.bot.get_cog("HorseRace")
            if hr_cog:
                await hr_cog.horse_race(interaction)
            else:
                await interaction.response.send_message("❌ Módulo de carreras no disponible.", ephemeral=True)
            return

        if val == "rps_bet":
            view = RPSUserSelectView(self.user, self.cog)
            embed = discord.Embed(
                title="⚔️ Duelo: Piedra, Papel o Tijeras",
                description="Selecciona al oponente que deseas retar de la lista de miembros:",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

        if val == "loto":
            loto_cog = self.cog.bot.get_cog("Loto")
            if loto_cog:
                await loto_cog.loto(interaction)
            else:
                await interaction.response.send_message("❌ Módulo de loto no disponible.", ephemeral=True)
            return

        if val == "provably_fair":
            pf_cog = self.cog.bot.get_cog("ProvablyFair")
            if pf_cog:
                await pf_cog.provably_fair_cmd(interaction)
            else:
                await interaction.response.send_message("❌ Módulo Provably Fair no disponible.", ephemeral=True)
            return

        names = {
            "slots": "Tragamonedas",
            "blackjack": "Blackjack",
            "roulette": "Ruleta",
            "crash": "Crash / Cohete",
            "mines": "Buscaminas",
            "plinko": "Plinko",
            "coinflip": "Coinflip",
            "casino_war": "Casino War",
            "higher_lower": "Higher or Lower",
            "liars_dice": "Dados de Mentiroso",
            "russian_roulette": "Ruleta Rusa"
        }
        name = names.get(val, "Juego")
        modal = QuickBetModal(val, name, self.cog)
        await interaction.response.send_modal(modal)



class RobarBandaSelectView(discord.ui.View):
    """Vista con menús desplegables nativos de miembros para Cómplice y Víctima."""
    def __init__(self, user: discord.Member, cog):
        super().__init__(timeout=60)
        self.user = user
        self.cog = cog
        self.complice = None

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="🤝 1. Selecciona a tu Cómplice de la lista...", row=0)
    async def select_complice(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta opción no es para ti.", ephemeral=True)
            return

        c = select.values[0]
        if not isinstance(c, discord.Member) and interaction.guild:
            c = interaction.guild.get_member(c.id) or c
        self.complice = c

        embed = discord.Embed(
            title="👥 Golpe Conjunto en Banda",
            description=f"✅ **Cómplice seleccionado:** {self.complice.mention}\n\nAhora selecciona a la **Víctima** en el menú de abajo:",
            color=discord.Color.dark_purple()
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="🎯 2. Selecciona a tu Víctima de la lista...", row=1)
    async def select_victim(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta opción no es para ti.", ephemeral=True)
            return

        if not self.complice:
            await interaction.response.send_message("⚠️ Primero debes seleccionar a tu Cómplice en el primer menú.", ephemeral=True)
            return

        victim = select.values[0]
        if not isinstance(victim, discord.Member) and interaction.guild:
            victim = interaction.guild.get_member(victim.id) or victim

        robar_cog = self.cog.bot.get_cog("Robar")
        if robar_cog:
            if hasattr(robar_cog.robar_banda_slash, "callback"):
                await robar_cog.robar_banda_slash.callback(robar_cog, interaction, self.complice, victim)
            else:
                await robar_cog.robar_banda_slash(interaction, self.complice, victim)
        else:
            await interaction.response.send_message("❌ Módulo de robos no disponible.", ephemeral=True)


class RobarSelectionView(discord.ui.View):
    """Vista con los 3 tipos de robo: Individual, En Banda y Banco Central."""
    def __init__(self, user: discord.Member, cog):
        super().__init__(timeout=60)
        self.user = user
        self.cog = cog

    @discord.ui.button(label="👤 Robo Individual", style=discord.ButtonStyle.danger, emoji="🗡️")
    async def rob_individual(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return
        view = RobarUserSelectView(self.user, self.cog)
        embed = discord.Embed(
            title="🥷 Robo Individual",
            description="Selecciona a la **víctima** de la lista desplegable de miembros para ejecutar el asalto:",
            color=discord.Color.dark_red()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="👥 Robo en Banda", style=discord.ButtonStyle.primary, emoji="🥷")
    async def rob_banda(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return
        view = RobarBandaSelectView(self.user, self.cog)
        embed = discord.Embed(
            title="👥 Golpe Conjunto en Banda",
            description="1. Selecciona a tu **Cómplice** de la lista.\n2. Selecciona a la **Víctima** de la lista.",
            color=discord.Color.dark_purple()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


    @discord.ui.button(label="🏦 Robo al Banco Central", style=discord.ButtonStyle.secondary, emoji="💰")
    async def rob_banco(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return
        robar_cog = self.cog.bot.get_cog("Robar")
        if robar_cog and hasattr(robar_cog, "robar_banco_slash"):
            if hasattr(robar_cog.robar_banco_slash, "callback"):
                await robar_cog.robar_banco_slash.callback(robar_cog, interaction, None)
            else:
                await robar_cog.robar_banco_slash(interaction, None)
        else:
            await interaction.response.send_message("❌ Módulo de robo al banco no disponible.", ephemeral=True)

    @discord.ui.button(label="📊 Perfil de Ladrón", style=discord.ButtonStyle.secondary, emoji="📋")
    async def rob_perfil(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return
        robar_cog = self.cog.bot.get_cog("Robar")
        if robar_cog:
            await robar_cog._perfil_ladron_logica(interaction)
        else:
            await interaction.response.send_message("❌ Módulo de perfil de ladrón no disponible.", ephemeral=True)



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

        view = RobarSelectionView(self.user, self.cog)
        embed = discord.Embed(
            title="🥷 Sub-sistema de Robos & Asaltos",
            description="Selecciona qué tipo de operativo criminal deseas realizar:",
            color=discord.Color.dark_red()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


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
            if hasattr(bolsa_cog.bolsa, "callback"):
                await bolsa_cog.bolsa.callback(bolsa_cog, interaction)
            else:
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
