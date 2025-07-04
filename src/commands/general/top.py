import discord
from discord.ext import commands
from discord import app_commands
import pyodbc
from db import conn_str
from db import ensure_user

class Top(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="top", description="Muestra el top de usuarios con más monedas en el servidor.")
    async def top(self, interaction: discord.Interaction):
        guild = interaction.guild
        user_id = interaction.user.id
        user_name = interaction.user.name
        ensure_user(user_id, user_name)  # Asegura registro y datos del usuario
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("SELECT UserID, Balance FROM Users ORDER BY Balance DESC")
        rows = cursor.fetchmany(20)
        conn.close()
        top_list = []
        for user_id, balance in rows:
            member = guild.get_member(user_id)
            if not member:
                try:
                    member = await guild.fetch_member(user_id)
                except Exception:
                    member = None
            if member:
                nombre = member.display_name
                top_list.append((nombre, balance))
            if len(top_list) >= 10:
                break
        if not top_list:
            await interaction.response.send_message("No hay usuarios con saldo en este servidor.")
            return
        desc = ""
        medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
        for i, (nombre, balance) in enumerate(top_list, 1):
            medal = medals[i-1] if i <= len(medals) else ""
            desc += f"{medal} **#{i}** {nombre} — `{balance}` monedas\n"
        embed = discord.Embed(
            title=f"🏆 Top 10 usuarios más ricos de {guild.name}",
            description=desc,
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=guild.icon.url if guild.icon else discord.Embed.Empty)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Top(bot))
    print("Top cog loaded successfully.")
