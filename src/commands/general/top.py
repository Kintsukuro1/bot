import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from src.db import ensure_user, db_cursor, get_top_minas

class Top(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="top", description="Muestra el top de usuarios con más monedas en el servidor.")
    async def top(self, interaction: discord.Interaction):
        guild = interaction.guild
        user_id = interaction.user.id
        user_name = interaction.user.name
        ensure_user(user_id, user_name)  # Asegura registro y datos del usuario
        
        # Obtener los IDs de los miembros del servidor para filtrar por base de datos
        member_ids = tuple(m.id for m in guild.members)
        
        await interaction.response.defer()
        
        try:
            # Ejecutar la consulta en un hilo secundario
            def query_top():
                with db_cursor() as cursor:
                    if member_ids:
                        if len(member_ids) == 1:
                            cursor.execute("SELECT UserID, Balance, UserName FROM Users WHERE UserID = %s ORDER BY Balance DESC LIMIT 10", (member_ids[0],))
                        else:
                            cursor.execute("SELECT UserID, Balance, UserName FROM Users WHERE UserID IN %s ORDER BY Balance DESC LIMIT 10", (member_ids,))
                    else:
                        cursor.execute("SELECT UserID, Balance, UserName FROM Users ORDER BY Balance DESC LIMIT 10")
                    return cursor.fetchall()
            
            rows = await asyncio.to_thread(query_top)
            
        except Exception as e:
            print(f"Error querying top users: {e}")
            await interaction.followup.send("❌ Ocurrió un error al obtener el ranking.", ephemeral=True)
            return
            
        top_list = []
        for db_user_id, balance, db_username in rows:
            member = guild.get_member(db_user_id)
            if member:
                nombre = member.display_name
            elif db_username:
                nombre = db_username
            else:
                nombre = f"Usuario {db_user_id}"
                
            top_list.append((nombre, balance))
                
        if not top_list:
            await interaction.followup.send("No hay usuarios con saldo en este servidor.")
            return
            
        desc = ""
        medals = ["🥇", "🥈", "🥉", "🏅", "🏅", "🏅", "🏅", "🏅", "🏅", "🏅"]
        
        # El máximo balance para calcular las barras de progreso
        max_balance = top_list[0][1] if top_list else 1
        max_balance = max(max_balance, 1) # Prevenir división por cero
        
        for i, (nombre, balance) in enumerate(top_list, 1):
            medal = medals[i-1] if i <= len(medals) else "🏅"
            
            # Crear una barra de progreso visual simple
            ratio = balance / max_balance
            filled_blocks = int(ratio * 10)
            empty_blocks = 10 - filled_blocks
            progress_bar = f"{'█' * filled_blocks}{'░' * empty_blocks}"
            
            desc += f"{medal} **{nombre}**\n"
            desc += f"└ 🪙 `{balance:,}` monedas | `{progress_bar}`\n\n"
            
        embed = discord.Embed(
            title=f"🏆 Top 10 usuarios más ricos",
            description=desc,
            color=discord.Color.gold()
        )
        embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
        embed.set_footer(text=f"Solicitado por {interaction.user.display_name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="top_minas", description="Muestra el top de usuarios que más minas han pisado en el servidor.")
    async def top_minas(self, interaction: discord.Interaction):
        guild = interaction.guild
        user_id = interaction.user.id
        user_name = interaction.user.name
        ensure_user(user_id, user_name)
        
        member_ids = tuple(m.id for m in guild.members)
        
        await interaction.response.defer()
        
        try:
            # Ejecutar la consulta en un hilo secundario
            rows = await asyncio.to_thread(get_top_minas, 10, member_ids)
            
        except Exception as e:
            print(f"Error querying top minas: {e}")
            await interaction.followup.send("❌ Ocurrió un error al obtener el ranking.", ephemeral=True)
            return
            
        top_list = []
        for db_user_id, minas_pisadas, db_username in rows:
            if minas_pisadas == 0:
                continue
                
            member = guild.get_member(db_user_id)
            if member:
                nombre = member.display_name
            elif db_username:
                nombre = db_username
            else:
                nombre = f"Usuario {db_user_id}"
                
            top_list.append((nombre, minas_pisadas))
                
        if not top_list:
            await interaction.followup.send("Nadie ha pisado ninguna mina en este servidor. ¡Qué paz!")
            return
            
        desc = ""
        medals = ["💥", "🤕", "🚑", "🩹", "🩹", "🩹", "🩹", "🩹", "🩹", "🩹"]
        
        for i, (nombre, minas_pisadas) in enumerate(top_list, 1):
            medal = medals[i-1] if i <= len(medals) else "🩹"
            desc += f"{medal} **{nombre}**: `{minas_pisadas}` minas pisadas\n\n"
            
        embed = discord.Embed(
            title=f"💣 Top Víctimas de Minas",
            description=desc,
            color=discord.Color.dark_red()
        )
        embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
        embed.set_footer(text=f"Solicitado por {interaction.user.display_name} - ¡Cuidado donde pisas!", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Top(bot))
    print("Top cog loaded successfully.")
