import discord
from discord.ext import commands
from discord import app_commands
from src.commands.shop.black_market_items import BLACK_MARKET

class BlackMarket(commands.Cog):
    """Cog para mostrar mejoras permanentes del mercado negro."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="blackmarket", description="Muestra las mejoras permanentes del mercado negro.")
    async def blackmarket(self, interaction: discord.Interaction):
        items = BLACK_MARKET
        embed = discord.Embed(
            title="🕶️ Black Market (Mejoras Permanentes)",
            description="Mejoras exclusivas para los más arriesgados.",
            color=discord.Color.dark_purple()
        )
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/3062/3062634.png")
        for item in items:
            embed.add_field(
                name=f"{item['nombre']} — {item['precio']} 🪙",
                value=f"`ID:` `{item['id']}`\n{item['descripcion']}",
                inline=False
            )
        embed.set_footer(text="Usa /comprar_mejora <ID> para adquirir una mejora permanente.")
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(BlackMarket(bot))
    print("BlackMarket cog loaded successfully.")
