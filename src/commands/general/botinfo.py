import discord
from discord.ext import commands

class Botinfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="botinfo", description="Muestra información sobre el bot.")
    async def botinfo(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🤖 Información del Bot",
            description="Basura creada por un bastardo",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Desarrollador", value="stockholmuser", inline=True)
        embed.add_field(name="Servidores", value=f"{len(self.bot.guilds)}", inline=True)
        embed.add_field(name="Usuarios", value=f"{sum(g.member_count for g in self.bot.guilds)}", inline=True)
        embed.add_field(name="Versión", value="1.0.0", inline=True)
        embed.set_footer(text="¡Por una tortura eterna!")
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Botinfo(bot))