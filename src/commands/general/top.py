import discord
from discord.ext import commands
from discord import app_commands
import logging
from src.services import UserService, LeaderboardService

logger = logging.getLogger(__name__)

class Top(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="top", description="Muestra el top de usuarios con más monedas en el servidor.")
    async def top(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Este comando solo puede usarse en un servidor.", ephemeral=True)
            return

        user_id = interaction.user.id
        user_name = interaction.user.name
        
        # Asegura registro y datos del usuario de forma asíncrona
        await UserService.ensure_user(user_id, user_name)
        
        # Obtener los IDs de los miembros del servidor para filtrar
        member_ids = tuple(m.id for m in guild.members)
        
        await interaction.response.defer()
        
        try:
            rows = await LeaderboardService.get_top_richest(member_ids, limit=10)
        except Exception as e:
            logger.error(f"Error querying top users: {e}", exc_info=True)
            await interaction.followup.send("❌ Ocurrió un error al obtener el ranking.", ephemeral=True)
            raise
            
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
            title="🏆 Top 10 usuarios más ricos",
            description=desc,
            color=discord.Color.gold()
        )
        embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
        embed.set_footer(text=f"Solicitado por {interaction.user.display_name}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="top_minas", description="Muestra el top de usuarios que más minas han pisado en el servidor.")
    async def top_minas(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Este comando solo puede usarse en un servidor.", ephemeral=True)
            return

        user_id = interaction.user.id
        user_name = interaction.user.name
        
        await UserService.ensure_user(user_id, user_name)
        
        member_ids = tuple(m.id for m in guild.members)
        
        await interaction.response.defer()
        
        try:
            rows = await LeaderboardService.get_top_minas_victims(member_ids, limit=10)
        except Exception as e:
            logger.error(f"Error querying top minas: {e}", exc_info=True)
            await interaction.followup.send("❌ Ocurrió un error al obtener el ranking.", ephemeral=True)
            raise
            
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
            title="💣 Top Víctimas de Minas",
            description=desc,
            color=discord.Color.dark_red()
        )
        embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)
        embed.set_footer(text=f"Solicitado por {interaction.user.display_name} - ¡Cuidado donde pisas!", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Top(bot))
    logger.info("Top cog loaded successfully.")
