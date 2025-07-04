import discord
from discord.ext import commands

class UserInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="userinfo", description="Muestra información de un usuario.")
    @discord.app_commands.describe(member="Usuario del que quieres ver la información")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        embed = discord.Embed(
            title=f"Información de {member.display_name}",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Nombre", value=str(member), inline=True)
        embed.add_field(name="Rol más alto", value=member.top_role.mention, inline=True)
        embed.add_field(name="Cuenta creada", value=member.created_at.strftime("%d/%m/%Y"), inline=True)
        embed.add_field(name="Se unió el", value=member.joined_at.strftime("%d/%m/%Y") if member.joined_at else "Desconocido", inline=True)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(UserInfo(bot))