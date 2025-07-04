import discord
from discord.ext import commands
import wavelink

class MusicSkip(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="skip", help="Salta la canción actual.")
    async def skip(self, ctx):
        player: wavelink.Player = wavelink.Pool.get_node().get_player(ctx.guild)
        if not player or not player.is_connected() or not player.current:
            await ctx.send("❌ No hay ninguna canción reproduciéndose.")
            return
        await player.skip()
        await ctx.send("⏭️ Canción saltada.")

async def setup(bot):
    await bot.add_cog(MusicSkip(bot))
    print("MusicSkip cog loaded successfully.")
