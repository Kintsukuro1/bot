import discord
from discord.ext import commands
from discord import app_commands
import random
from src.db import get_balance, set_balance, ensure_user, usuario_tiene_item, usuario_tiene_mejora

class Slots(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="slots", description="Juega a las tragamonedas y prueba tu suerte.")
    @app_commands.describe(apuesta="Cantidad a apostar")
    async def slots(self, interaction: discord.Interaction, apuesta: int):
        try:
            user_id = interaction.user.id
            user_name = interaction.user.name
            ensure_user(user_id, user_name)  # Asegura registro y datos del usuario
            saldo_usuario = get_balance(user_id)

            if apuesta <= 0:
                await interaction.response.send_message("La apuesta debe ser mayor a 0.", ephemeral=True)
                return
            if apuesta > saldo_usuario:
                await interaction.response.send_message("No tienes suficiente saldo para esa apuesta.", ephemeral=True)
                return

            symbols = ['🍒', '🍋', '🔔', '⭐', '💎', '🍉', '🍇', '🍀']
            result = [random.choice(symbols) for _ in range(3)]
            result_display = ' | '.join(result)

            # --- MEJORAS BLACK MARKET ---
            prob_bonus = 0.0
            ganancia_bonus = 1.0
            if usuario_tiene_mejora(user_id, 1):  # Suerte Eterna
                prob_bonus += 0.10
            if usuario_tiene_mejora(user_id, 3):  # Magnate
                ganancia_bonus += 0.10
            # ---------------------------

            gano = len(set(result)) == 1
            if not gano and prob_bonus > 0 and random.random() < prob_bonus:
                gano = True  # Aplica el bonus de probabilidad

            if gano:
                ganancia = int(apuesta * ganancia_bonus)
                set_balance(user_id, saldo_usuario + ganancia)
                title = '🎰 ¡Felicidades! ¡Has ganado!'
                color = discord.Color.green()
                footer = '¡Has acertado los 3 símbolos!'
            else:
                set_balance(user_id, saldo_usuario - apuesta)
                title = '🎰 Lo siento, has perdido.'
                color = discord.Color.red()
                footer = 'Inténtalo de nuevo.'
            embed = discord.Embed(
                title=title,
                description=f'{result_display}\n\nApuesta: **{apuesta}**\nSaldo actual: **{get_balance(user_id)}**',
                color=color
            )
            embed.set_footer(text=footer)
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"Ocurrió un error: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Slots(bot))
