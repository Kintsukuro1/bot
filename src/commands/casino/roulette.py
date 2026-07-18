import asyncio
import random
import discord
from discord.ext import commands
from discord import app_commands

from src.db import ensure_user
from src.services.casino_service import CasinoService
from src.commands.economy.pets import process_post_game_events
from src.utils.dynamic_difficulty import DynamicDifficulty

RED_NUMBERS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
BLACK_NUMBERS = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]


class RouletteBetSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Rojo (Red)", description="Pago x2", emoji="🔴", value="red"),
            discord.SelectOption(label="Negro (Black)", description="Pago x2", emoji="⚫", value="black"),
            discord.SelectOption(label="Par (Even)", description="Pago x2", emoji="🔢", value="even"),
            discord.SelectOption(label="Impar (Odd)", description="Pago x2", emoji="🔢", value="odd"),
            discord.SelectOption(label="Primera Mitad (1-18)", description="Pago x2", emoji="⬇️", value="first_half"),
            discord.SelectOption(label="Segunda Mitad (19-36)", description="Pago x2", emoji="⬆️", value="second_half"),
            discord.SelectOption(label="Primera Docena (1-12)", description="Pago x3", emoji="1️⃣", value="dozen_1"),
            discord.SelectOption(label="Segunda Docena (13-24)", description="Pago x3", emoji="2️⃣", value="dozen_2"),
            discord.SelectOption(label="Tercera Docena (25-36)", description="Pago x3", emoji="3️⃣", value="dozen_3")
        ]
        super().__init__(placeholder="Elige tu apuesta...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, RouletteView) or interaction.user.id != view.user_id:
            await interaction.response.send_message("¡Esta no es tu partida!", ephemeral=True)
            return
        await view.process_spin(interaction, self.values[0])


class RouletteView(discord.ui.View):
    def __init__(self, user_id: int, bet_amount: int, difficulty_modifier: float, balance: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.difficulty_modifier = difficulty_modifier
        self.balance = balance
        self.spinning = False
        self.message: discord.Message | None = None
        self.add_item(RouletteBetSelect())

    async def on_timeout(self):
        for item in self.children:
            try:
                item.disabled = True  # type: ignore[attr-defined]
            except AttributeError:
                pass
        await CasinoService.refund_bet(self.user_id, self.bet_amount, 'roulette', 'Timeout sin elegir apuesta')
        if self.message:
            try:
                embed = self.message.embeds[0]
                embed.color = discord.Color.dark_grey()
                embed.description = "El crupier cerró la mesa porque tardaste demasiado."
                embed.set_footer(text="Tu apuesta te ha sido devuelta.")
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass

    def check_win(self, bet_type: str, winning_number: int) -> float:
        if winning_number == 0:
            return 0.0
        if bet_type == "red" and winning_number in RED_NUMBERS:
            return 2.0
        if bet_type == "black" and winning_number in BLACK_NUMBERS:
            return 2.0
        if bet_type == "even" and winning_number % 2 == 0:
            return 2.0
        if bet_type == "odd" and winning_number % 2 != 0:
            return 2.0
        if bet_type == "first_half" and 1 <= winning_number <= 18:
            return 2.0
        if bet_type == "second_half" and 19 <= winning_number <= 36:
            return 2.0
        if bet_type == "dozen_1" and 1 <= winning_number <= 12:
            return 3.0
        if bet_type == "dozen_2" and 13 <= winning_number <= 24:
            return 3.0
        if bet_type == "dozen_3" and 25 <= winning_number <= 36:
            return 3.0
        return 0.0

    async def process_spin(self, interaction: discord.Interaction, bet_type: str):
        if self.spinning:
            try:
                await interaction.response.send_message("⚠️ Ya hay un giro en proceso. Por favor, espera a que termine.", ephemeral=True)
            except Exception:
                pass
            return

        self.spinning = True
        self.stop()

        for item in self.children:
            try:
                item.disabled = True  # type: ignore[attr-defined]
            except AttributeError:
                pass

        embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else discord.Embed()
        embed.description = f"Has apostado **{self.bet_amount}** a **{bet_type}**.\n\n🎡 La ruleta está girando..."

        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            try:
                if interaction.message:
                    await interaction.message.edit(embed=embed, view=self)
            except Exception:
                pass

        try:
            await asyncio.sleep(2)

            winning_number = random.randint(0, 36)
            win_color = "🟢" if winning_number == 0 else ("🔴" if winning_number in RED_NUMBERS else "⚫")
            multiplier = self.check_win(bet_type, winning_number)

            mult_adjustment = 1.0 - (self.difficulty_modifier * 0.15)
            mult_adjustment = max(0.80, min(1.20, mult_adjustment))
            winnings = int(self.bet_amount * multiplier * mult_adjustment)
            profit = winnings - self.bet_amount

            if multiplier > 0:
                nuevo_saldo = await CasinoService.settle_win(
                    self.user_id,
                    self.bet_amount,
                    winnings,
                    'roulette',
                    self.difficulty_modifier,
                    self.balance
                )
                try:
                    await process_post_game_events(interaction, self.user_id, 'roulette', self.bet_amount, profit)
                except Exception:
                    pass
                embed.color = discord.Color.green()
                embed.title = "🎰 Ruleta - ¡Ganaste!"
                embed.description = (
                    f"La bola cayó en: **{win_color} {winning_number}**\n\n"
                    f"Multiplicador: **x{multiplier}**\n"
                    f"Premio: **{winnings}** monedas (Beneficio: **+{profit}**)")
                embed.description += f"\nNuevo saldo: **{nuevo_saldo}**"
            else:
                nuevo_saldo = await CasinoService.settle_loss(
                    self.user_id,
                    self.bet_amount,
                    'roulette',
                    self.difficulty_modifier,
                    self.balance
                )
                try:
                    await process_post_game_events(interaction, self.user_id, 'roulette', self.bet_amount, 0)
                except Exception:
                    pass
                embed.color = discord.Color.red()
                embed.title = "🎰 Ruleta - Perdiste"
                embed.description = (
                    f"La bola cayó en: **{win_color} {winning_number}**\n\n"
                    f"Perdiste **{self.bet_amount}** monedas.")
                embed.description += f"\nNuevo saldo: **{nuevo_saldo}**"

            try:
                await interaction.edit_original_response(embed=embed, view=self)
            except Exception:
                try:
                    if interaction.message:
                        await interaction.message.edit(embed=embed, view=self)
                except Exception:
                    pass

        except Exception as e:
            print(f"Error crítico en Ruleta (process_spin): {e}")
            try:
                await CasinoService.refund_bet(self.user_id, self.bet_amount, 'roulette', 'Error de sistema')
            except Exception as db_err:
                print(f"Error al intentar reembolsar tras fallo en Ruleta: {db_err}")

            embed.color = discord.Color.orange()
            embed.title = "⚠️ Ruleta - Mesa Cerrada"
            embed.description = (
                f"Ocurrió un error inesperado al procesar el giro de la ruleta.\n"
                f"**Tu apuesta de {self.bet_amount} monedas ha sido devuelta.**"
            )
            try:
                await interaction.edit_original_response(embed=embed, view=self)
            except Exception:
                try:
                    if interaction.message:
                        await interaction.message.edit(embed=embed, view=self)
                except Exception:
                    pass


class Roulette(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="roulette", description="Juega a la Ruleta Europea.")
    @app_commands.describe(apuesta="Cantidad de monedas a apostar")
    async def roulette(self, interaction: discord.Interaction, apuesta: int):
        user_id = interaction.user.id
        user_name = interaction.user.name

        if apuesta <= 0:
            await interaction.response.send_message("❌ La apuesta debe ser mayor a 0.", ephemeral=True)
            return

        await asyncio.to_thread(ensure_user, user_id, user_name)

        success, saldo_usuario = await CasinoService.place_bet(user_id, apuesta, 'roulette')
        if not success:
            await interaction.response.send_message("❌ No tienes suficiente saldo para esa apuesta.", ephemeral=True)
            return

        difficulty_modifier, _ = await asyncio.to_thread(
            DynamicDifficulty.calculate_dynamic_difficulty, user_id, apuesta, 'roulette'
        )

        view = RouletteView(user_id, apuesta, difficulty_modifier, saldo_usuario)

        embed = discord.Embed(
            title="🎡 Ruleta Europea",
            description=(
                f"Has puesto en la mesa **{apuesta}** monedas.\n\n"
                "Elige a qué quieres apostar usando el menú. Tienes 60 segundos."
            ),
            color=discord.Color.dark_green()
        )
        embed.set_footer(text="Haz tus apuestas.")

        await interaction.response.send_message(embed=embed, view=view)
        try:
            view.message = await interaction.original_response()
        except Exception as e:
            print(f"Error al obtener original_response en roulette: {e}")


async def setup(bot):
    await bot.add_cog(Roulette(bot))
    print("Roulette cog cargado con éxito.")
