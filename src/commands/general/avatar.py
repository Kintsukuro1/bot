import discord
from discord.ext import commands

class Avatar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="avatar", description="Muestra el avatar de un usuario.")
    @discord.app_commands.describe(member="Usuario del que quieres ver el avatar")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        embed = discord.Embed(
            title=f"Avatar de {member.display_name}",
            color=discord.Color.blue()
        )
        embed.set_image(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Avatar(bot))