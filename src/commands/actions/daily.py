import discord
from discord.ext import commands
from datetime import datetime, timedelta
import sys
import os
import pyodbc

# Obtener la ruta al directorio 'discord-bot'
base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if base_path not in sys.path:
    sys.path.insert(0, base_path)

from src.db import get_balance, ensure_user, add_balance, conn_str

class Daily(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="daily", description="Reclama tu recompensa diaria.")
    async def daily(self, interaction: discord.Interaction):
        """Reclama tu recompensa diaria."""
        user_id = interaction.user.id
        user_name = interaction.user.name
        ensure_user(user_id, user_name)  # Asegura registro y datos del usuario
        try:
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()

            # Obtener la última fecha de inicio de sesión y el contador de días consecutivos
            cursor.execute("SELECT LastLogin, Streak FROM Users WHERE UserID = ?", user_id)
            row = cursor.fetchone()

            today = datetime.now().date()

            if row:
                last_login, streak = row
                if isinstance(last_login, datetime):
                    last_login = last_login.date()
                else:
                    try:
                        last_login = datetime.strptime(str(last_login), '%Y-%m-%d').date()
                    except Exception:
                        last_login = today - timedelta(days=2)
            else:
                last_login, streak = None, 0

            if last_login == today:
                now = datetime.now()
                next_day = datetime.combine(today + timedelta(days=1), datetime.min.time())
                time_remaining = next_day - now
                hours, remainder = divmod(time_remaining.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                embed = discord.Embed(
                    title="⏳ Ya has reclamado tu recompensa diaria hoy",
                    description=f"Vuelve en **{hours}h {minutes}m {seconds}s** para reclamar de nuevo.",
                    color=discord.Color.orange()
                )
                await interaction.response.send_message(embed=embed)
                conn.close()
                return

            if last_login and (today - last_login).days == 1:
                streak += 1
            else:
                streak = 1

            reward = 100 * (streak // 7 + 1)

            cursor.execute("""
                UPDATE Users SET LastLogin = ?, Streak = ? WHERE UserID = ?
            """, today, streak, user_id)
            conn.commit()
            conn.close()

            add_balance(user_id, reward)

            embed = discord.Embed(
                title="🎁 ¡Recompensa diaria reclamada!",
                description=f"Has recibido **{reward}** monedas.\nRacha: **{streak}** días.\nSaldo actual: **{get_balance(user_id)}**",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"Ocurrió un error al reclamar la recompensa diaria: {e}", ephemeral=True)

# Añadir el cog al bot
async def setup(bot):
    await bot.add_cog(Daily(bot))
    print("Daily cog cargado con éxito")
