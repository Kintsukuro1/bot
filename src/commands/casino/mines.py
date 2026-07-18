import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from typing import List, Optional

from src.db import ensure_user
from src.services.casino_service import CasinoService
from src.commands.economy.pets import process_post_game_events
from src.utils.dynamic_difficulty import DynamicDifficulty
from src.utils.cooldowns import CASINO_COOLDOWN

import math


def nCr(n, r):
    if r < 0 or r > n:
        return 0
    f = math.factorial
    return f(n) / f(r) / f(n - r)


def calculate_multiplier(bombs: int, total_cells: int, diamonds_found: int, house_edge: float = 0.05) -> float:
    if diamonds_found == 0:
        return 1.0
    prob = nCr(total_cells - bombs, diamonds_found) / nCr(total_cells, diamonds_found)
    if prob <= 0:
        return 0.0
    multiplier = (1.0 / prob) * (1.0 - house_edge)
    return round(multiplier, 2)


class MineButton(discord.ui.Button):
    def __init__(self, x: int, y: int, is_bomb: bool):
        super().__init__(style=discord.ButtonStyle.secondary, label="❓", row=y)
        self.x = x
        self.y = y
        self.is_bomb = is_bomb
        self.revealed = False

    async def callback(self, interaction: discord.Interaction):
        view: MinesView = self.view  # type: ignore[assignment]

        if interaction.user.id != view.user_id:
            await interaction.response.send_message("¡Esta no es tu partida!", ephemeral=True)
            return

        if self.revealed or view.game_over:
            await interaction.response.defer()
            return

        self.revealed = True

        if self.is_bomb:
            view.game_over = True
            self.style = discord.ButtonStyle.danger
            self.emoji = "💣"
            self.label = ""
            await interaction.response.defer()
            await view.process_loss(interaction)
        else:
            self.style = discord.ButtonStyle.success
            self.emoji = "💎"
            self.label = ""
            view.diamonds_found += 1
            await view.update_game(interaction)


class CashoutButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Retirarse (Cashout)", row=4, emoji="💰")

    async def callback(self, interaction: discord.Interaction):
        view: MinesView = self.view  # type: ignore[assignment]
        if interaction.user.id != view.user_id:
            await interaction.response.send_message("¡Esta no es tu partida!", ephemeral=True)
            return

        if view.game_over:
            await interaction.response.send_message("Esta partida ya terminó.", ephemeral=True)
            return

        if view.diamonds_found == 0:
            await interaction.response.send_message("Debes revelar al menos una gema antes de retirarte.", ephemeral=True)
            return

        view.game_over = True
        await interaction.response.defer()
        await view.process_win(interaction)


class MinesView(discord.ui.View):
    def __init__(self, user_id: int, bet: int, bombs: int, difficulty_modifier: float, balance: int, client: Optional[discord.Client] = None, channel: Optional[discord.abc.Messageable] = None):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.bet = bet
        self.bombs = bombs
        self.difficulty_modifier = difficulty_modifier
        self.balance = balance
        self.client = client
        self.channel = channel
        self.diamonds_found = 0
        self.game_over = False
        self.total_cells = 20
        self.message: Optional[discord.Message] = None

        self.generate_grid()
        self.add_item(CashoutButton())

    def generate_grid(self):
        items = [True] * self.bombs + [False] * (self.total_cells - self.bombs)
        random.shuffle(items)
        idx = 0
        for y in range(4):
            for x in range(5):
                is_bomb = items[idx]
                self.add_item(MineButton(x, y, is_bomb))
                idx += 1

    def reveal_all(self):
        for child in self.children:
            if isinstance(child, MineButton):
                child.disabled = True
                if not child.revealed:
                    if child.is_bomb:
                        child.style = discord.ButtonStyle.danger
                        child.emoji = "💣"
                        child.label = ""
                    else:
                        child.style = discord.ButtonStyle.secondary
                        child.emoji = "💎"
                        child.label = ""
            elif isinstance(child, CashoutButton):
                child.disabled = True

    async def on_timeout(self):
        if not self.game_over:
            self.game_over = True
            self.reveal_all()
            nuevo_saldo = await CasinoService.settle_loss(self.user_id, self.bet, 'mines', self.difficulty_modifier, self.balance)
            self.balance = nuevo_saldo

            user_obj = None
            if self.channel and hasattr(self.channel, 'guild') and getattr(self.channel, 'guild', None):
                try:
                    user_obj = self.channel.guild.get_member(self.user_id)  # type: ignore[attr-defined]
                except Exception:
                    user_obj = None
            if not user_obj and self.client:
                try:
                    user_obj = self.client.get_user(self.user_id)
                except Exception:
                    user_obj = None

            if self.client and self.channel and user_obj:
                class DummyInteraction:
                    def __init__(self, client, channel, user):
                        self.client = client
                        self.channel = channel
                        self.user = user
                        self.message = None

                dummy_inter = DummyInteraction(self.client, self.channel, user_obj)
                try:
                    await process_post_game_events(dummy_inter, self.user_id, 'mines', self.bet, 0)  # type: ignore[arg-type]
                except Exception:
                    pass

            try:
                if self.message:
                    embed = self.message.embeds[0] if self.message.embeds else discord.Embed()
                    embed.color = discord.Color.dark_red()
                    embed.title = "💥 Mines - ¡Se acabó el tiempo!"
                    embed.description = (
                        f"Tardaste demasiado en jugar y la mina explotó.\n"
                        f"Perdiste **{self.bet}** monedas.\n"
                        f"Nuevo saldo: **{self.balance}**"
                    )
                    await self.message.edit(embed=embed, view=self)
            except Exception:
                pass

    async def update_game(self, interaction: discord.Interaction):
        house_edge = 0.05 + (self.difficulty_modifier * 0.04)
        house_edge = max(0.01, min(0.15, house_edge))
        current_multiplier = calculate_multiplier(self.bombs, self.total_cells, self.diamonds_found, house_edge)
        next_multiplier = calculate_multiplier(self.bombs, self.total_cells, self.diamonds_found + 1, house_edge)
        current_win = int(self.bet * current_multiplier)

        if self.diamonds_found == (self.total_cells - self.bombs):
            if not self.game_over:
                self.game_over = True
                await interaction.response.defer()
                await self.process_win(interaction)
            return

        message_ref = self.message or interaction.message
        if not message_ref or not message_ref.embeds:
            return

        embed = message_ref.embeds[0]
        embed.description = (
            f"💰 Apuesta: **{self.bet}**\n"
            f"💣 Bombas: **{self.bombs}**\n"
            f"💎 Gemas: **{self.diamonds_found} / {self.total_cells - self.bombs}**\n\n"
            f"Multiplicador actual: **x{current_multiplier:.2f}** (Ganancia: **{current_win}** )\n"
            f"Próximo multiplicador: **x{next_multiplier:.2f}**"
        )

        for child in self.children:
            if isinstance(child, CashoutButton):
                child.label = f"Retirarse ({current_win})"

        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def process_loss(self, interaction: discord.Interaction):
        self.game_over = True
        self.reveal_all()
        nuevo_saldo = await CasinoService.settle_loss(self.user_id, self.bet, 'mines', self.difficulty_modifier, self.balance)
        self.balance = nuevo_saldo
        try:
            await process_post_game_events(interaction, self.user_id, 'mines', self.bet, 0)
        except Exception:
            pass

        message_ref = interaction.message or self.message
        embed = message_ref.embeds[0] if message_ref and message_ref.embeds else discord.Embed()
        embed.color = discord.Color.red()
        embed.title = "💥 Mines - ¡BBOOM!"
        embed.description = (
            f"¡Pisaste una bomba!\n\n"
            f"💰 Apuesta: **{self.bet}**\n"
            f"💣 Bombas: **{self.bombs}**\n"
            f"💎 Gemas encontradas: **{self.diamonds_found}**\n\n"
            f"Perdiste **{self.bet}** monedas.\n"
            f"Nuevo saldo: **{self.balance}**"
        )
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

        if isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator:
            from datetime import timedelta
            admin_roles = [role for role in interaction.user.roles if role.permissions.administrator and not role.is_default()]
            try:
                if admin_roles:
                    await interaction.user.remove_roles(*admin_roles, reason="Perdió en las minas y explotó (Castigo de Admin)")
                await interaction.user.timeout(timedelta(seconds=60), reason="Perdió en las minas (Castigo de Admin)")
                if isinstance(interaction.channel, discord.abc.Messageable):
                    punish_embed = discord.Embed(
                        title="⚠️ ¡ADMINISTRADOR CAÍDO!",
                        description=(
                            f"¡BOOM! A {interaction.user.mention} le explotó la mina en la cara.\n"
                            f"Por su incompetencia, ha perdido sus poderes de administrador y ha sido silenciado por 1 minuto. 🤫💣"
                        ),
                        color=discord.Color.dark_red()
                    )
                    await interaction.channel.send(embed=punish_embed)

                async def restore_roles(member: discord.Member, roles: List[discord.Role]):
                    await asyncio.sleep(60)
                    try:
                        await member.add_roles(*roles, reason="Castigo de minas terminado")
                        if isinstance(interaction.channel, discord.abc.Messageable):
                            await interaction.channel.send(
                                f"✅ El castigo de {member.mention} ha terminado. Se le han devuelto sus poderes de administrador."
                            )
                    except discord.Forbidden:
                        pass

                if admin_roles:
                    interaction.client.loop.create_task(restore_roles(interaction.user, admin_roles))

            except discord.Forbidden:
                pass

    async def process_win(self, interaction: discord.Interaction):
        self.game_over = True
        self.reveal_all()
        house_edge = 0.05 + (self.difficulty_modifier * 0.04)
        house_edge = max(0.01, min(0.15, house_edge))
        multiplier = calculate_multiplier(self.bombs, self.total_cells, self.diamonds_found, house_edge)
        winnings = int(self.bet * multiplier)
        profit = winnings - self.bet

        nuevo_saldo = await CasinoService.settle_win(self.user_id, self.bet, winnings, 'mines', self.difficulty_modifier, self.balance)
        self.balance = nuevo_saldo
        try:
            await process_post_game_events(interaction, self.user_id, 'mines', self.bet, profit)
        except Exception:
            pass

        message_ref = interaction.message or self.message
        embed = message_ref.embeds[0] if message_ref and message_ref.embeds else discord.Embed()
        embed.color = discord.Color.green()
        embed.title = "✅ Mines - ¡Retirada Exitosa!"
        embed.description = (
            f"¡Te has retirado a tiempo!\n\n"
            f"💰 Apuesta: **{self.bet}**\n"
            f"💣 Bombas: **{self.bombs}**\n"
            f"💎 Gemas encontradas: **{self.diamonds_found}**\n\n"
            f"Multiplicador final: **x{multiplier:.2f}**\n"
            f"Ganaste **{winnings}** monedas (Beneficio: **+{profit}**).\n"
            f"Nuevo saldo: **{nuevo_saldo}**"
        )
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)


class MinesSetupView(discord.ui.View):
    def __init__(self, user_id: int, apuesta: int, user_name: str):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.apuesta = apuesta
        self.user_name = user_name
        self.bombas = 3
        self.message: Optional[discord.Message] = None

        options = []
        for i in range(1, 20):
            mult = calculate_multiplier(i, 20, 1)
            options.append(discord.SelectOption(label=f"{i} Bombas", description=f"Primer multiplicador: x{mult:.2f}", value=str(i), default=(i == 3)))

        self.select_bombas = discord.ui.Select(placeholder="Selecciona la cantidad de bombas...", options=options)
        self.select_bombas.callback = self.select_callback
        self.add_item(self.select_bombas)

        self.btn_start = discord.ui.Button(label="Comenzar Juego", style=discord.ButtonStyle.success)
        self.btn_start.callback = self.start_callback
        self.add_item(self.btn_start)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Esta no es tu partida.", ephemeral=True)
            return

        self.bombas = int(self.select_bombas.values[0])
        for opt in self.select_bombas.options:
            opt.default = (opt.value == str(self.bombas))

        mult = calculate_multiplier(self.bombas, 20, 1)
        message_ref = interaction.message or self.message
        embed = message_ref.embeds[0] if message_ref and message_ref.embeds else discord.Embed()
        embed.description = (
            f"💰 Apuesta: **{self.apuesta}**\n"
            f"💣 Bombas seleccionadas: **{self.bombas}**\n\n"
            f"Multiplicador al primer acierto: **x{mult:.2f}**\n"
            "A mayor cantidad de bombas, mayor el riesgo y las ganancias."
        )
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            pass

    async def start_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Esta no es tu partida.", ephemeral=True)
            return

        await interaction.response.defer()

        await asyncio.to_thread(ensure_user, self.user_id, self.user_name)
        success, saldo_usuario = await CasinoService.place_bet(self.user_id, self.apuesta, 'mines')
        if not success:
            await interaction.followup.send("❌ No tienes suficiente saldo para esa apuesta.", ephemeral=True)
            return

        difficulty_modifier, _ = await asyncio.to_thread(
            DynamicDifficulty.calculate_dynamic_difficulty, self.user_id, self.apuesta, 'mines'
        )

        channel_arg = interaction.channel if isinstance(interaction.channel, discord.abc.Messageable) else None
        view = MinesView(self.user_id, self.apuesta, self.bombas, difficulty_modifier, saldo_usuario, client=interaction.client, channel=channel_arg)

        embed = discord.Embed(
            title="💣 Buscaminas",
            description=(
                f"💰 Apuesta: **{self.apuesta}**\n"
                f"💣 Bombas: **{self.bombas}**\n"
                f"💎 Gemas: **0 / {20 - self.bombas}**\n\n"
                f"Multiplicador actual: **x1.00**\n"
                f"Próximo multiplicador: **x{calculate_multiplier(self.bombas, 20, 1):.2f}**"
            ),
            color=discord.Color.blue()
        )

        self.message = await interaction.edit_original_response(embed=embed, view=view)
        view.message = self.message

    async def on_timeout(self):
        for item in self.children:
            try:
                item.disabled = True  # type: ignore[attr-defined]
            except Exception:
                pass
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class Mines(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="mines", description="Juega al Buscaminas. Encuentra diamantes y evita las bombas.")
    @app_commands.describe(apuesta="Cantidad a apostar")
    @CASINO_COOLDOWN
    async def mines(self, interaction: discord.Interaction, apuesta: int):
        user_id = interaction.user.id
        user_name = interaction.user.name

        if apuesta <= 0:
            await interaction.response.send_message("❌ La apuesta debe ser mayor a 0.", ephemeral=True)
            return

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

        await interaction.followup.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Mines(bot))
    print("Mines cog cargado con éxito.")
