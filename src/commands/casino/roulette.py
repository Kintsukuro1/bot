import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio

from src.db import get_balance, set_balance, deduct_balance, add_balance, ensure_user, registrar_transaccion, record_game_result
from src.utils.dynamic_difficulty import DynamicDifficulty

# Definición de números
ROULETTE_NUMBERS = list(range(0, 37))
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
        view: RouletteView = self.view
        if interaction.user.id != view.user_id:
            await interaction.response.send_message("¡Esta no es tu partida!", ephemeral=True)
            return

        bet_type = self.values[0]
        await view.process_spin(interaction, bet_type)

class RouletteView(discord.ui.View):
    def __init__(self, user_id: int, bet_amount: int, difficulty_modifier: float, balance: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.difficulty_modifier = difficulty_modifier
        self.balance = balance
        self.add_item(RouletteBetSelect())
        self.message = None

    async def on_timeout(self):
        # Si no hizo ninguna apuesta
        for item in self.children:
            item.disabled = True
            
        await asyncio.to_thread(add_balance, self.user_id, self.bet_amount)
        
        try:
            if self.message:
                embed = self.message.embeds[0]
                embed.color = discord.Color.dark_grey()
                embed.description = "El crupier cerró la mesa porque tardaste demasiado."
                embed.set_footer(text="Tu apuesta te ha sido devuelta.")
                await self.message.edit(embed=embed, view=self)
        except:
            pass

    def check_win(self, bet_type: str, winning_number: int) -> float:
        if winning_number == 0:
            return 0.0 # 0 gana la casa en todas las apuestas externas
            
        if bet_type == "red" and winning_number in RED_NUMBERS: return 2.0
        if bet_type == "black" and winning_number in BLACK_NUMBERS: return 2.0
        if bet_type == "even" and winning_number % 2 == 0: return 2.0
        if bet_type == "odd" and winning_number % 2 != 0: return 2.0
        if bet_type == "first_half" and 1 <= winning_number <= 18: return 2.0
        if bet_type == "second_half" and 19 <= winning_number <= 36: return 2.0
        if bet_type == "dozen_1" and 1 <= winning_number <= 12: return 3.0
        if bet_type == "dozen_2" and 13 <= winning_number <= 24: return 3.0
        if bet_type == "dozen_3" and 25 <= winning_number <= 36: return 3.0
        
        return 0.0

    async def process_spin(self, interaction: discord.Interaction, bet_type: str):
        # Deshabilitar vista
        for item in self.children:
            item.disabled = True
            
        embed = interaction.message.embeds[0]
        embed.description = f"Has apostado **{self.bet_amount}** a **{bet_type}**.\n\n🎡 La ruleta está girando..."
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Simular giro
        await asyncio.sleep(2)
        
        # Tirar número
        winning_number = random.randint(0, 36)
        
        # Aplicar Dificultad (Redraw)
        # Si la dificultad es positiva (difícil), y gana, pequeña chance de reroll a algo perdedor
        # Si es negativa (fácil), y pierde, pequeña chance de reroll a algo ganador
        multiplier = self.check_win(bet_type, winning_number)
        
        if self.difficulty_modifier > 0 and multiplier > 0:
            if random.random() < self.difficulty_modifier * 0.4:
                winning_number = random.randint(0, 36)
                multiplier = self.check_win(bet_type, winning_number)
        elif self.difficulty_modifier < 0 and multiplier == 0:
            if random.random() < abs(self.difficulty_modifier) * 0.3:
                winning_number = random.randint(0, 36)
                multiplier = self.check_win(bet_type, winning_number)

        # Evaluar color del número ganador
        if winning_number == 0:
            win_color = "🟢"
        elif winning_number in RED_NUMBERS:
            win_color = "🔴"
        else:
            win_color = "⚫"

        winnings = int(self.bet_amount * multiplier)
        profit = winnings - self.bet_amount

        if multiplier > 0:
            # Gana
            nuevo_saldo = self.balance + winnings
            await asyncio.to_thread(add_balance, self.user_id, winnings)
            await asyncio.to_thread(registrar_transaccion, self.user_id, profit, f"Ruleta: Ganó apostando a {bet_type}")
            await asyncio.to_thread(record_game_result, self.user_id, 'roulette', self.bet_amount, 'win', profit, self.difficulty_modifier, nuevo_saldo)
            
            embed.color = discord.Color.green()
            embed.title = "🎰 Ruleta - ¡Ganaste!"
            embed.description = (
                f"La bola cayó en: **{win_color} {winning_number}**\n\n"
                f"Multiplicador: **x{multiplier}**\n"
                f"Premio: **{winnings}** monedas (Beneficio: **+{profit}**)\n"
                f"Nuevo saldo: **{nuevo_saldo}**"
            )
        else:
            # Pierde
            nuevo_saldo = self.balance
            await asyncio.to_thread(registrar_transaccion, self.user_id, -self.bet_amount, f"Ruleta: Perdió apostando a {bet_type}")
            await asyncio.to_thread(record_game_result, self.user_id, 'roulette', self.bet_amount, 'loss', 0, self.difficulty_modifier, nuevo_saldo)
            
            embed.color = discord.Color.red()
            embed.title = "🎰 Ruleta - Perdiste"
            embed.description = (
                f"La bola cayó en: **{win_color} {winning_number}**\n\n"
                f"Perdiste **{self.bet_amount}** monedas.\n"
                f"Nuevo saldo: **{nuevo_saldo}**"
            )

        await interaction.message.edit(embed=embed, view=self)


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
        
        success, saldo_usuario = await asyncio.to_thread(deduct_balance, user_id, apuesta)
        if not success:
            await interaction.response.send_message("❌ No tienes suficiente saldo para esa apuesta.", ephemeral=True)
            return

        # Calcular dificultad
        difficulty_modifier, explanation = await asyncio.to_thread(
            DynamicDifficulty.calculate_dynamic_difficulty, user_id, apuesta, 'roulette'
        )

        view = RouletteView(user_id, apuesta, difficulty_modifier, saldo_usuario)
        
        embed = discord.Embed(
            title="🎡 Ruleta Europea",
            description=f"Has puesto en la mesa **{apuesta}** monedas.\n\nPor favor, elige a qué quieres apostar utilizando el menú de abajo. Tienes 60 segundos.",
            color=discord.Color.dark_green()
        )
        embed.set_footer(text="Haz tus apuestas.")
        
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

async def setup(bot):
    await bot.add_cog(Roulette(bot))
    print("Roulette cog cargado con éxito.")
